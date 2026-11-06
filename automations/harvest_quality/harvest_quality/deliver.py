"""POST the PDF. n8n answers immediately; a 2xx means the file was accepted."""

import httpx


def post_pdf(
    url: str,
    pdf: bytes,
    *,
    file_field: str,
    force_field: str,
    force_value: str,
    force: bool,
    pdf_name: str = "calidad-cosecha.pdf",
    timeout: float = 60,
) -> int:
    files = {file_field: (pdf_name, pdf, "application/pdf")}
    data = {force_field: force_value} if force else None
    response = httpx.post(url, files=files, data=data, timeout=timeout)
    response.raise_for_status()
    return response.status_code
