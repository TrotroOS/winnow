"""Map raw source dicts to ``Candidate`` and deduplicate without scoring.

``normalize`` copies only explicit keys from ``raw`` — missing string fields become
``""``, missing ``signals`` / ``contacts`` become ``{}``. Name and org are never
inferred from other fields. Missing ``collected_at`` is set to Unix epoch UTC
(``1970-01-01T00:00:00+00:00``) as a documented sentinel; it is not guessed from
other data.

``dedupe`` collapses duplicate rows by key:

- Non-empty ``id`` (after strip): key is that id (case-insensitive). Treat ids as
  source-unique record identifiers when the adapter supplies them.
- Empty ``id``: key is ``(name.lower().strip(), org.lower().strip())``.

For each key the survivor is the row with the greatest ``collected_at``. Ties keep
the earliest-seen row among those tied at the newest timestamp. Output order follows
the first input index of each key (stable survivor slots).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from winnow.models import Candidate

_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _string_field(raw: dict, key: str) -> str:
    value = raw.get(key)
    if value is None:
        return ""
    return str(value)


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(k): "" if v is None else str(v)
        for k, v in value.items()
        if isinstance(k, str)
    }


def _parse_collected_at(value: object) -> datetime:
    if value is None:
        return _EPOCH_UTC
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        if not value.strip():
            return _EPOCH_UTC
        return datetime.fromisoformat(value)
    return _EPOCH_UTC


def normalize(raw: dict, source: str) -> Candidate:
    """Build a ``Candidate`` from a source payload without inferring missing fields."""
    return Candidate(
        id=_string_field(raw, "id"),
        name=_string_field(raw, "name"),
        org=_string_field(raw, "org"),
        role=_string_field(raw, "role"),
        signals=_string_dict(raw.get("signals")),
        contacts=_string_dict(raw.get("contacts")),
        source=source,
        collected_at=_parse_collected_at(raw.get("collected_at")),
    )


def _dedupe_key(candidate: Candidate) -> tuple[str, ...]:
    id_stripped = candidate.id.strip()
    if id_stripped:
        return ("id", id_stripped.lower())
    return (
        "person",
        candidate.name.lower().strip(),
        candidate.org.lower().strip(),
    )


def _newer(a: Candidate, b: Candidate) -> Candidate:
    if a.collected_at > b.collected_at:
        return a
    return b


def dedupe(candidates: Sequence[Candidate]) -> tuple[list[Candidate], int]:
    """Return ``(survivors, dropped_count)`` with stable first-seen key order."""
    if not candidates:
        return [], 0

    first_index: dict[tuple[str, ...], int] = {}
    best: dict[tuple[str, ...], Candidate] = {}

    for index, candidate in enumerate(candidates):
        key = _dedupe_key(candidate)
        if key not in first_index:
            first_index[key] = index
            best[key] = candidate
            continue
        best[key] = _newer(candidate, best[key])

    ordered_keys = sorted(best.keys(), key=lambda k: first_index[k])
    survivors = [best[k] for k in ordered_keys]
    dropped = len(candidates) - len(survivors)
    return survivors, dropped