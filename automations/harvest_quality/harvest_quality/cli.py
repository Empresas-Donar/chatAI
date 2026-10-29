"""run respects the Chile clock. now sends once to production, outside the clock."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from harvest_quality.config import ROOT
from harvest_quality.config import load_yaml
from harvest_quality.decision import ENVIADO
from harvest_quality.decision import SIN_DATOS
from harvest_quality.decision import decide
from harvest_quality.deliver import post_pdf
from harvest_quality.pages import split_pages
from harvest_quality.report import download_report
from harvest_quality.report import save_session
from harvest_quality.schedule import is_due
from harvest_quality.schedule import needs_n8n_force
from harvest_quality.state import connect
from harvest_quality.state import insert_check
from harvest_quality.state import last_sent_huella

log = logging.getLogger("harvest_quality")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in {"run", "now", "session"}:
        print("usage: python -m harvest_quality run|now|session", file=sys.stderr)
        return 2
    try:
        if args[0] == "session":
            return capture_session()
        return execute(args[0])
    except Exception:
        log.exception("harvest quality check failed")
        return 1


def capture_session() -> int:
    job = load_yaml("job.yaml")
    dest = ROOT / ".session" / "state.json"
    save_session(job["report_url"], dest)
    log.info("session saved at %s", dest)
    return 0


def execute(mode: str) -> int:
    job = load_yaml("job.yaml")
    n8n = load_yaml("n8n.yaml")
    now = datetime.now(ZoneInfo(job["timezone"]))
    if mode == "run" and not is_due(now, list(job["hours"]), int(job["grace_minutes"])):
        log.info("outside Chile window %s", now.isoformat())
        return 0

    pdf = download_report(job["report_url"])
    kept, huella = split_pages(pdf, job["empty_marker"])
    proceso = job["proceso"]
    conn = connect()
    try:
        last = last_sent_huella(conn, proceso)
        # now is the manual probe: send even when the fingerprint already went out.
        motivo = (ENVIADO if huella else SIN_DATOS) if mode == "now" else decide(huella, last)
        enviado = motivo == ENVIADO
        enviado_en = now if enviado else None
        if enviado:
            status = post_pdf(
                n8n["production_url"],
                kept,
                file_field=n8n["file_field"],
                force_field=n8n["force_field"],
                force_value=str(n8n["force_value"]),
                force=mode == "now" or needs_n8n_force(now.hour),
            )
            log.info("posted %s status=%s", mode, status)
        row_id = insert_check(
            conn,
            proceso=proceso,
            huella=huella,
            enviado=enviado,
            motivo=motivo,
            revisado_en=now,
            enviado_en=enviado_en,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    log.info("recorded %s motivo=%s", row_id, motivo)
    return 0
