"""
controllers/csv_migrator_controller.py
---------------------------------------
HTTP layer for the CSV → PostgreSQL migration feature.

Routes:
  GET  /                    → Migration UI
  POST /upload              → Upload CSVs, returns analysis JSON
  POST /sync/start          → Start background sync job
  GET  /sync/stream/{id}    → SSE log stream
  POST /sync/stop/{id}      → Cancel running job
"""

import asyncio
import json
import logging
import shutil
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from auth import require_auth
from models.migration_models import SyncResult, TableAnalysis
from services.csv_parser import parse_csv
from services.sync_service import create_log_queue, get_log_queue, remove_log_queue, sync

logger = logging.getLogger("controllers.csv_migrator")

router = APIRouter(dependencies=[Depends(require_auth)])

_upload_dir: Path = None
_templates: Jinja2Templates = None
_sessions: dict[str, dict] = {}
_jobs: dict[str, dict] = {}
_stream_tokens: dict[str, str] = {}


def init(upload_dir: Path, templates: Jinja2Templates) -> None:
    global _upload_dir, _templates
    _upload_dir = upload_dir
    _templates = templates


@router.get("/migrador", response_class=HTMLResponse)
async def migrador_page(request: Request):
    return _templates.TemplateResponse(request, "index.html")


@router.post("/upload")
async def upload(
    app_name: str = Form(...),
    files: list[UploadFile] = File(...),
):
    import re
    app_name = app_name.strip()
    if not app_name:
        raise HTTPException(status_code=400, detail="app_name is required")
    if not re.match(r'^[a-zA-Z0-9_\-]+$', app_name):
        raise HTTPException(status_code=400, detail="app_name must contain only letters, digits, underscores and hyphens")

    session_id = str(uuid.uuid4())
    session_dir = _upload_dir / session_id
    session_dir.mkdir(parents=True)

    analyses: list[TableAnalysis] = []
    errors: list[str] = []

    for upload in files:
        if not upload.filename.endswith(".csv"):
            errors.append(f"{upload.filename}: only CSV files accepted")
            continue
        dest = session_dir / upload.filename
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        try:
            analyses.append(parse_csv(dest, app_name))
            logger.info(f"Parsed {upload.filename}: {analyses[-1].row_count} rows")
        except Exception as exc:
            errors.append(f"{upload.filename}: {exc}")

    if not analyses and errors:
        raise HTTPException(status_code=422, detail=errors)

    _sessions[session_id] = {"app_name": app_name.strip(), "analyses": analyses}
    (session_dir / "app_name.txt").write_text(app_name.strip(), encoding="utf-8")

    return {
        "session_id": session_id,
        "app_name": app_name.strip(),
        "errors": errors,
        "tables": [_serialize(a) for a in analyses],
    }


@router.post("/sync/start")
async def sync_start(
    session_id: str = Form(...),
    dry_run: bool = Form(False),
):
    session = _sessions.get(session_id) or _restore_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please re-upload.")

    job_id = str(uuid.uuid4())
    stopped = threading.Event()
    log_q = create_log_queue(job_id)
    _jobs[job_id] = {"stopped": stopped, "result": None, "done": False}

    def run():
        try:
            result = sync(
                app_name=session["app_name"],
                analyses=session["analyses"],
                dry_run=dry_run,
                job_id=job_id,
                stopped=stopped,
            )
            _jobs[job_id]["result"] = result
        except Exception as exc:
            logger.error(f"Job {job_id} failed: {exc}")
            log_q.put(f"FATAL ERROR: {exc}")
            log_q.put(None)
        finally:
            _jobs[job_id]["done"] = True
            if not dry_run and session_id in _sessions:
                del _sessions[session_id]
                _cleanup(session_id)

    threading.Thread(target=run, daemon=True).start()
    token = str(uuid.uuid4())
    _stream_tokens[token] = job_id
    return {"job_id": job_id, "stream_token": token}


@router.get("/sync/stream/{job_id}", dependencies=[])
async def sync_stream(job_id: str, token: str = ""):
    if _stream_tokens.pop(token, None) != job_id:
        raise HTTPException(status_code=403, detail="Invalid or expired stream token")
    log_q = get_log_queue(job_id)
    if not log_q:
        raise HTTPException(status_code=404, detail="Job not found")

    async def events():
        loop = asyncio.get_event_loop()
        try:
            while True:
                try:
                    msg = await loop.run_in_executor(None, lambda: log_q.get(timeout=0.5))
                except Exception:
                    if _jobs.get(job_id, {}).get("done") and log_q.empty():
                        break
                    continue
                if msg is None:
                    result: Optional[SyncResult] = _jobs.get(job_id, {}).get("result")
                    if result:
                        payload = json.dumps({
                            "app_name": result.app_name,
                            "dry_run": result.dry_run,
                            "total_inserted": result.total_inserted,
                            "tables": [
                                {"table_name": t.table_name, "success": t.success,
                                 "rows_inserted": t.rows_inserted, "error": t.error}
                                for t in result.tables
                            ],
                        })
                        yield f"event: result\ndata: {payload}\n\n"
                    yield "event: done\ndata: done\n\n"
                    break
                else:
                    yield f"data: {msg}\n\n"
        finally:
            remove_log_queue(job_id)
            _jobs.pop(job_id, None)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sync/stop/{job_id}")
async def sync_stop(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job["stopped"].set()
    return {"status": "stopping"}


def _serialize(a: TableAnalysis) -> dict:
    return {
        "table_name": a.table_name,
        "filename": a.filename,
        "row_count": a.row_count,
        "column_count": a.column_count,
        "warnings": a.warnings,
        "columns": [
            {"name": c.name, "pg_type": c.pg_type,
             "empty_count": c.empty_count, "empty_ratio": round(c.empty_ratio, 3),
             "warnings": c.warnings}
            for c in a.columns
        ],
        "preview": a.preview,
    }


def _restore_session(session_id: str) -> Optional[dict]:
    session_dir = _upload_dir / session_id
    app_name_file = session_dir / "app_name.txt"
    if not session_dir.exists() or not app_name_file.exists():
        return None
    app_name = app_name_file.read_text(encoding="utf-8").strip()
    analyses = []
    for f in sorted(session_dir.glob("*.csv")):
        try:
            analyses.append(parse_csv(f, app_name))
        except Exception as exc:
            logger.warning(f"Could not restore {f.name}: {exc}")
    if not analyses:
        return None
    session = {"app_name": app_name, "analyses": analyses}
    _sessions[session_id] = session
    logger.info(f"Restored session {session_id} ({len(analyses)} tables)")
    return session


def _cleanup(session_id: str) -> None:
    d = _upload_dir / session_id
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
