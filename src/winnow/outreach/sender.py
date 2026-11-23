"""Build and confirm outreach batches."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from winnow.models import Candidate, Criteria, OutreachSummary
from winnow.outreach.batcher import primary_channel, recipient_for
from winnow.outreach.suppression import SuppressionStore
from winnow.outreach.templates import TEMPLATE_VERSION, build_message
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


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    candidate_id: str
    channel: str
    recipient: str
    body: str
    situation_type: str
    template_version: str


@dataclass
class SendBatch:
    batch_id: str
    messages: list[OutboundMessage] = field(default_factory=list)


@dataclass
class OutreachSender:
    transport: Transport
    suppression: SuppressionStore
    throttle: Throttle
    tracker: OutreachTracker
    _pending: dict[str, SendBatch] = field(default_factory=dict)

    def build_batch(
        self,
        *,
        situation_type: str,
        possible: Sequence[Candidate],
        criteria: Sequence[Criteria],
        manual_approve: bool = True,
    ) -> SendBatch:
        """Stage messages for POSSIBLE candidates only (manual mode sends nothing yet)."""
        batch_id = str(uuid.uuid4())
        messages: list[OutboundMessage] = []
        for candidate in possible:
            if self.suppression.is_suppressed(candidate.id):
                continue
            channel = primary_channel(candidate)
            if channel is None:
                continue
            body = build_message(situation_type, candidate, criteria)
            messages.append(
                OutboundMessage(
                    candidate_id=candidate.id,
                    channel=channel,
                    recipient=recipient_for(candidate, channel),
                    body=body,
                    situation_type=situation_type,
                    template_version=TEMPLATE_VERSION,
                )
            )
        batch = SendBatch(batch_id=batch_id, messages=messages)
        if manual_approve:
            self._pending[batch_id] = batch
            return batch
        self._deliver(batch)
        return batch

    def confirm_send(self, batch_id: str) -> OutreachSummary:
        """Send a previously built batch (manual approval path)."""
        try:
            batch = self._pending.pop(batch_id)
        except KeyError as exc:
            raise KeyError(f"unknown batch {batch_id!r}") from exc
        return self._deliver(batch)

    def _deliver(self, batch: SendBatch) -> OutreachSummary:
        sent = 0
        suppressed = 0
        skipped = 0
        for message in batch.messages:
            if self.suppression.is_suppressed(message.candidate_id):
                suppressed += 1
                continue
            if not self.throttle.allow(message.channel):
                skipped += 1
                continue
            self.transport.send(
                message.channel,
                message.recipient,
                message.body,
                candidate_id=message.candidate_id,
            )
            self.suppression.mark_contacted(message.candidate_id)
            self.throttle.record(message.channel)
            self.tracker.record_sent(
                message.candidate_id,
                template_version=message.template_version,
            )
            sent += 1
        return OutreachSummary(
            sent=sent,
            replied=0,
            bounced=0,
            suppressed=suppressed,
            skipped=skipped,
        )