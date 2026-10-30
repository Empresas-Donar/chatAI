"""Download every page of the Looker report with a saved Google session."""

import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger("harvest_quality")

# First try plus five retries when Looker does not hand over the PDF.
DOWNLOAD_ATTEMPTS = 6


class SessionMissing(RuntimeError):
    pass


def run_attempts(action, attempts: int = DOWNLOAD_ATTEMPTS):
    """Call action until it returns. A missing session is not retried."""
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except SessionMissing:
            raise
        except Exception:
            log.warning("Looker PDF attempt %s/%s failed", attempt, attempts)
            if attempt == attempts:
                raise


def save_session(report_url: str, dest: Path) -> None:
    """Open normal Chrome so a person can log in once. Writes Playwright state.

    A fresh Playwright context is incognito. The report link opens there without
    an account, and Google refuses that login. Installed Chrome with its own
    profile accepts the Google sign-in.
    """
    from playwright.sync_api import sync_playwright

    dest.parent.mkdir(parents=True, exist_ok=True)
    profile = dest.parent / "chrome-profile"
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            channel="chrome",
            headless=False,
            ignore_default_args=["--enable-automation"],
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://accounts.google.com/", wait_until="domcontentloaded", timeout=120_000)
        input("Entra a Google en esta ventana. Cuando veas tu correo, vuelve aquí y pulsa Enter. ")
        page.goto(report_url, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(3000)
        context.storage_state(path=str(dest))
        context.close()


def download_report(report_url: str, timeout_ms: int = 180_000, timezone: str = "America/Santiago") -> bytes:
    raw = os.environ.get("HARVEST_QUALITY_SESSION", "").strip()
    if not raw:
        raise SessionMissing("HARVEST_QUALITY_SESSION is empty")
    return run_attempts(lambda: _download_once(raw, report_url, timeout_ms, timezone))


def _download_once(raw: str, report_url: str, timeout_ms: int, timezone: str) -> bytes:
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as folder:
        state = Path(folder) / "state.json"
        state.write_text(raw, encoding="utf-8")
        dest = Path(folder) / "report.pdf"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=str(state),
                accept_downloads=True,
                timezone_id=timezone,
            )
            page = context.new_page()
            page.goto(report_url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                close = page.get_by_role("button", name="Cerrar")
                if close.count():
                    close.first.click(timeout=2_000)
            except Exception:
                pass
            page.get_by_role("button", name="Más opciones").click()
            page.get_by_role("menuitem", name="Descargar informe").click()
            with page.expect_download(timeout=timeout_ms) as download_info:
                page.get_by_role("button", name="Descargar", exact=True).click()
            download_info.value.save_as(dest)
            browser.close()
        return dest.read_bytes()
