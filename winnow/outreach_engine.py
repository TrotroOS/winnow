"""Outreach to POSSIBLE candidates only (stub)."""

from __future__ import annotations

from winnow.models import Candidate, OutreachCounts


def run_outreach(
    possible: list[Candidate],
    suppressed_ids: set[str] | None = None,
) -> OutreachCounts:
    """Stub: one outreach action per non-suppressed POSSIBLE candidate."""
    suppressed = suppressed_ids or set()
    counts = OutreachCounts()
    for candidate in possible:
        if candidate.id in suppressed:
            counts.suppressed += 1
            continue
        counts.sent += 1
    return counts