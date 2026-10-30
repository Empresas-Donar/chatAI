"""Keep Looker pages that have worker rows. Drop a sheet whose table says it is empty."""

from __future__ import annotations

import re
from io import BytesIO

from pypdf import PdfReader, PdfWriter

from harvest_quality.fingerprint import fingerprint_text, normalize

_NUMBER = re.compile(r"\d+(?:[,.]\d+)?")


def _has_worker_row(text: str) -> bool:
    """A worker row is several measurements on one line. The column title is not a row."""
    for line in text.splitlines():
        cleaned = line.lower().replace("no hay datos", " ").replace("no data", " ")
        if len(_NUMBER.findall(cleaned)) >= 4:
            return True
    return False


def page_is_empty(text: str, empty_marker: str) -> bool:
    """Drop the sheet when it says there is no data and the table has no worker rows."""
    body = text or ""
    lowered = body.lower()
    markers = [empty_marker.lower(), "no data"]
    if not any(marker and marker in lowered for marker in markers):
        return False
    return not _has_worker_row(body)


def split_pages(pdf: bytes, empty_marker: str) -> tuple[bytes, str | None]:
    reader = PdfReader(BytesIO(pdf))
    writer = PdfWriter()
    texts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if page_is_empty(text, empty_marker):
            continue
        writer.add_page(page)
        texts.append(normalize(text))
    if not writer.pages:
        return b"", None
    out = BytesIO()
    writer.write(out)
    huella = fingerprint_text("\n".join(part for part in texts if part))
    return out.getvalue(), huella
