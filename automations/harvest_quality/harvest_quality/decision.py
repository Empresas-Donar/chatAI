"""Send or skip. The last successful fingerprint is the baseline."""

from __future__ import annotations

SIN_DATOS = "sin_datos"
SIN_CAMBIOS = "sin_cambios"
ENVIADO = "enviado"


def decide(huella: str | None, last_sent: str | None) -> str:
    if not huella:
        return SIN_DATOS
    if huella == last_sent:
        return SIN_CAMBIOS
    return ENVIADO
