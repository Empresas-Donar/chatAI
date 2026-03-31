"""
main.py
-------
FastAPI application for the AppSheet → PostgreSQL web migrator.

Endpoints:
  GET  /                          → Main UI
  POST /upload                    → Upload CSVs, returns analysis JSON
  POST /sync/start                → Start sync job, returns job_id
  GET  /sync/stream/{job_id}      → SSE stream of log lines
  POST /sync/stop/{job_id}        → Cancel a running job
  GET  /health                    → Health check
"""

import logging
import shutil
import sys
import threading
import uuid
from pathlib import Path

# Add backend/ to sys.path so sibling modules resolve
sys.path.insert(0, str(Path(__file__).parent))

from pathlib import Path
from typing import Optional

# Load .env automatically
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

import asyncio
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from auth import require_auth
from csv_parser import TableAnalysis, parse_csv
from sync_service import (
    SyncResult, sync,
    create_log_queue, get_log_queue, remove_log_queue,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR   = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

FRONTEND_DIR  = BASE_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR    = FRONTEND_DIR / "static"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AppSheet → PostgreSQL Migrator",
    version="1.0.0",
    dependencies=[Depends(require_auth)],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Session store: session_id → {app_name, analyses}
_sessions: dict[str, dict] = {}

# Job store: job_id → {thread, stopped_event, result}
_jobs: dict[str, dict] = {}

# Stream tokens: token → job_id (one-time use, for SSE auth)
_stream_tokens: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload_csvs(
    app_name: str = Form(...),
    files: list[UploadFile] = File(...),
):
    if not app_name.strip():
        raise HTTPException(status_code=400, detail="app_name is required")

    session_id = str(uuid.uuid4())
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(parents=True)

    analyses: list[TableAnalysis] = []
    errors: list[str] = []

    for upload in files:
        if not upload.filename.endswith(".csv"):
            errors.append(f"{upload.filename}: only CSV files are accepted")
            continue

        dest = session_dir / upload.filename
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)

        try:
            analysis = parse_csv(dest, app_name)
            analyses.append(analysis)
            logger.info(f"Parsed {upload.filename}: {analysis.row_count} rows")
        except Exception as exc:
            errors.append(f"{upload.filename}: {exc}")

    if not analyses and errors:
        raise HTTPException(status_code=422, detail=errors)

    _sessions[session_id] = {"app_name": app_name.strip(), "analyses": analyses}

    # Persist app_name to disk so session survives server restarts
    (session_dir / "app_name.txt").write_text(app_name.strip(), encoding="utf-8")

    return {
        "session_id": session_id,
        "app_name": app_name.strip(),
        "errors": errors,
        "tables": [_serialize_analysis(a) for a in analyses],
    }


@app.post("/sync/start")
async def sync_start(
    session_id: str = Form(...),
    dry_run: bool = Form(False),
):
    """
    Start a sync job in a background thread.
    Returns job_id immediately — client polls /sync/stream/{job_id} for logs.
    """
    session = _sessions.get(session_id) or _restore_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please re-upload.")

    job_id = str(uuid.uuid4())
    stopped = threading.Event()
    log_q = create_log_queue(job_id)

    _jobs[job_id] = {"stopped": stopped, "result": None, "done": False}

    def run_sync():
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
            # Clean up session after real sync
            if not dry_run and session_id in _sessions:
                del _sessions[session_id]
                _cleanup_session_dir(session_id)

    thread = threading.Thread(target=run_sync, daemon=True)
    _jobs[job_id]["thread"] = thread
    thread.start()

    stream_token = str(uuid.uuid4())
    _stream_tokens[stream_token] = job_id

    return {"job_id": job_id, "stream_token": stream_token}


@app.get("/sync/stream/{job_id}", dependencies=[])
async def sync_stream(job_id: str, token: str = ""):
    """
    SSE endpoint — streams log lines from the sync job to the browser.
    Protected by a one-time stream_token (EventSource cannot send Basic Auth headers).
    """
    expected_job = _stream_tokens.pop(token, None)
    if expected_job != job_id:
        raise HTTPException(status_code=403, detail="Invalid or expired stream token")

    log_q = get_log_queue(job_id)
    if not log_q:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        loop = asyncio.get_event_loop()
        try:
            while True:
                # Non-blocking get with short sleep to keep event loop free
                try:
                    msg = await loop.run_in_executor(None, lambda: log_q.get(timeout=0.5))
                except Exception:
                    # timeout — check if job is done
                    job = _jobs.get(job_id, {})
                    if job.get("done") and log_q.empty():
                        break
                    continue

                if msg is None:
                    # Sentinel — job finished, send final result
                    job = _jobs.get(job_id, {})
                    result: Optional[SyncResult] = job.get("result")
                    if result:
                        import json
                        payload = json.dumps({
                            "app_name": result.app_name,
                            "dry_run": result.dry_run,
                            "total_inserted": result.total_inserted,
                            "tables": [
                                {
                                    "table_name": t.table_name,
                                    "success": t.success,
                                    "rows_inserted": t.rows_inserted,
                                    "error": t.error,
                                }
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
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/sync/stop/{job_id}")
async def sync_stop(job_id: str):
    """Signal a running job to stop."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job["stopped"].set()
    return {"status": "stopping"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_analysis(a: TableAnalysis) -> dict:
    return {
        "table_name": a.table_name,
        "filename": a.filename,
        "row_count": a.row_count,
        "column_count": a.column_count,
        "warnings": a.warnings,
        "columns": [
            {
                "name": c.name,
                "pg_type": c.pg_type,
                "empty_count": c.empty_count,
                "empty_ratio": round(c.empty_ratio, 3),
                "warnings": c.warnings,
            }
            for c in a.columns
        ],
        "preview": a.preview,
    }


def _restore_session(session_id: str) -> Optional[dict]:
    """
    Rebuild a session from disk if the server was restarted.
    CSVs are already in uploads/<session_id>/; app_name is in app_name.txt.
    """
    session_dir = UPLOAD_DIR / session_id
    app_name_file = session_dir / "app_name.txt"
    if not session_dir.exists() or not app_name_file.exists():
        return None

    app_name = app_name_file.read_text(encoding="utf-8").strip()
    analyses = []
    for csv_file in sorted(session_dir.glob("*.csv")):
        try:
            analysis = parse_csv(csv_file, app_name)
            analyses.append(analysis)
        except Exception as exc:
            logger.warning(f"Could not restore {csv_file.name}: {exc}")

    if not analyses:
        return None

    session = {"app_name": app_name, "analyses": analyses}
    _sessions[session_id] = session  # cache back in RAM
    logger.info(f"Restored session {session_id} from disk ({len(analyses)} tables)")
    return session


def _cleanup_session_dir(session_id: str) -> None:
    session_dir = UPLOAD_DIR / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)
