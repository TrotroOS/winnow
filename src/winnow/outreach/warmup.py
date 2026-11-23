"""Domain warm-up: ramp daily send cap toward configured ceiling."""

from __future__ import annotations

from datetime import date, datetime, timezone


def effective_daily_cap(
    *,
    ceiling: int,
    warmup_start_daily_cap: int,
    warmup_step: int,
    warmup_start_date: str | None = None,
    today: date | None = None,
) -> int:
    """Return today's email cap: ``min(ceiling, start + step * days)``."""
    day = today or datetime.now(timezone.utc).date()
    if warmup_start_date:
        start = date.fromisoformat(warmup_start_date)
    else:
        start = day
    days = max(0, (day - start).days)
    warmed = warmup_start_daily_cap + warmup_step * days
    return min(ceiling, warmed)