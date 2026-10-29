"""Chile clock gate. The GitHub cron is wider on purpose (UTC-3 and UTC-4)."""

from __future__ import annotations

from datetime import datetime


def needs_n8n_force(hour: int) -> bool:
    """n8n drops files outside 08:00–16:59 Chile unless forzar=1."""
    return hour >= 17


def is_due(moment: datetime, hours: list[int], grace_minutes: int) -> bool:
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    return moment.hour in hours and 0 <= moment.minute <= grace_minutes
