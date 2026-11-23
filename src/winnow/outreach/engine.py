"""Orchestrator-facing outreach entry: batch, manual approve, send."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from winnow.models import Candidate, Criteria, OutreachSummary
from winnow.outreach.sender import OutreachSender
from winnow.outreach.suppression import SuppressionStore
from winnow.outreach.throttle import Throttle
from winnow.outreach.tracker import OutreachTracker


class Transport(Protocol):
    def send(
        self,
        channel: str,
        recipient: str,
        body: str,
        *,
        candidate_id: str,
    ) -> None: ...


@dataclass
class NoopTransport:
    def send(
        self,
        channel: str,
        recipient: str,
        body: str,
        *,
        candidate_id: str,
    ) -> None:
        del channel, recipient, body, candidate_id


def _chunked(rows: Sequence[Candidate], batch_size: int) -> list[Sequence[Candidate]]:
    if batch_size <= 0 or batch_size >= len(rows):
        return [rows]
    return [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]


def run_outreach(
    possible: Sequence[Candidate],
    *,
    situation_type: str,
    criteria: Sequence[Criteria],
    batch_size: int,
    manual_approve: bool,
    suppressed_ids: frozenset[str] = frozenset(),
    transport: Transport | None = None,
) -> OutreachSummary:
    """Stage POSSIBLE rows in batches; send immediately or hold for manual approval."""
    sender = OutreachSender(
        transport=transport or NoopTransport(),
        suppression=SuppressionStore(),
        throttle=Throttle(
            caps={"email": 10_000, "linkedin": 10_000, "dm": 10_000},
        ),
        tracker=OutreachTracker(),
    )
    for candidate_id in suppressed_ids:
        sender.suppression.mark_contacted(candidate_id)

    sent = replied = bounced = suppressed = skipped = 0
    for chunk in _chunked(tuple(possible), batch_size):
        if not chunk:
            continue
        batch = sender.build_batch(
            situation_type=situation_type,
            possible=chunk,
            criteria=criteria,
            manual_approve=True,
        )
        if manual_approve:
            skipped += len(batch.messages)
            continue
        summary = sender.confirm_send(batch.batch_id)
        sent += summary.sent
        replied += summary.replied
        bounced += summary.bounced
        suppressed += summary.suppressed
        skipped += summary.skipped

    return OutreachSummary(
        sent=sent,
        replied=replied,
        bounced=bounced,
        suppressed=suppressed,
        skipped=skipped,
    )