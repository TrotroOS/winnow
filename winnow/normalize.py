"""Normalize raw records into Candidate instances."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from winnow.models import Candidate


def _parse_collected_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def normalize_record(record: dict[str, Any], source: str) -> Candidate:
    """Map a source record to a Candidate."""
    return Candidate(
        id=str(record.get("id", "")),
        name=str(record.get("name", "")).strip(),
        org=str(record.get("org", "")).strip(),
        role=str(record.get("role", "")).strip(),
        signals=dict(record.get("signals") or {}),
        contacts=dict(record.get("contacts") or {}),
        source=source,
        collected_at=_parse_collected_at(record.get("collected_at")),
    )


def normalize_batch(records: list[dict[str, Any]], source: str) -> list[Candidate]:
    return [normalize_record(r, source) for r in records]