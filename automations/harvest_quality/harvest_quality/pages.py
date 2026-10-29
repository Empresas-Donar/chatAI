"""Drop Looker pages whose text contains the empty marker."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader, PdfWriter

from harvest_quality.fingerprint import fingerprint_text, normalize


def split_pages(pdf: bytes, empty_marker: str) -> tuple[bytes, str | None]:
    reader = PdfReader(BytesIO(pdf))
    writer = PdfWriter()
    texts: list[str] = []
    marker = empty_marker.lower()
    for page in reader.pages:
        text = page.extract_text() or ""
        if marker in text.lower():
            continue
        writer.add_page(page)
        texts.append(normalize(text))
    if not writer.pages:
        return b"", None
    out = BytesIO()
    writer.write(out)
    huella = fingerprint_text("\n".join(part for part in texts if part))
    return out.getvalue(), huella
