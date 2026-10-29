"""Hash the report text. Looker's 'last updated' line is not a data change."""

from __future__ import annotations

import hashlib
import re

_STAMP = re.compile(r"ltima actualizaci[oó]n", re.IGNORECASE)


def normalize(text: str) -> str:
    kept = []
    for line in (text or "").splitlines():
        if _STAMP.search(line):
            continue
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            kept.append(cleaned)
    return "\n".join(kept)


def fingerprint_text(text: str) -> str | None:
    body = normalize(text)
    if not body:
        return None
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
