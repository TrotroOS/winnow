"""Batched outreach for POSSIBLE candidates only (no triage)."""

from __future__ import annotations

from collections.abc import Sequence

from winnow.models import Candidate, OutreachSummary


def run_outreach(
    possible: Sequence[Candidate],
    *,
    batch_size: int,
    manual_approve: bool,
    suppressed_ids: frozenset[str] = frozenset(),
) -> OutreachSummary:
    """One outreach action per POSSIBLE row; batches are sizing hints only."""
    if batch_size <= 0:
        batch_size = len(possible) or 1

    sent = suppressed = skipped = 0
    if manual_approve:
        return OutreachSummary(skipped=len(possible))

    for candidate in possible:
        if candidate.id in suppressed_ids:
            suppressed += 1
            continue
        sent += 1

    return OutreachSummary(sent=sent, suppressed=suppressed)