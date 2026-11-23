"""Build and confirm outreach batches."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from winnow.models import Candidate, Criteria, OutreachSummary
from winnow.outreach.batcher import CHANNEL_PRIORITY, primary_channel, recipient_for
from winnow.outreach.personalize import MatchedSignalError
from winnow.outreach.transport_linkedin import (
    DEFAULT_MATCHED_SIGNAL_MAX_AGE_DAYS,
    SECOND_CHANNEL,
    linkedin_candidate_eligible,
)
from winnow.outreach.suppression import SuppressionStore
from winnow.outreach.templates import TEMPLATE_VERSION, build_message
from winnow.outreach.throttle import Throttle
from winnow.outreach.guards import sends_halted
from winnow.outreach.tracker import OutreachTracker
from winnow.store import WinnowStore


class Transport(Protocol):
    def send(
        self,
        channel: str,
        recipient: str,
        body: str,
        *,
        candidate_id: str,
    ) -> str: ...


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
    per_run_send_cap: int | None = None
    store: WinnowStore | None = None
    run_id: int | None = None
    _pending: dict[str, SendBatch] = field(default_factory=dict)
    _sent_this_run: int = field(default=0, init=False)

    def build_batch(
        self,
        *,
        situation_type: str,
        possible: Sequence[Candidate],
        criteria: Sequence[Criteria],
        manual_approve: bool = True,
        channel_priority: tuple[str, ...] | None = None,
        filter_now: datetime | None = None,
        linkedin_max_signal_age_days: int = DEFAULT_MATCHED_SIGNAL_MAX_AGE_DAYS,
    ) -> SendBatch:
        """Stage messages for POSSIBLE candidates only (manual mode sends nothing yet)."""
        batch_id = str(uuid.uuid4())
        messages: list[OutboundMessage] = []
        priority = channel_priority or CHANNEL_PRIORITY
        for candidate in possible:
            if self.suppression.is_suppressed(candidate.id):
                continue
            channel = primary_channel(candidate, priority=priority)
            if channel is None:
                continue
            if channel == SECOND_CHANNEL:
                if not linkedin_candidate_eligible(
                    candidate,
                    criteria,
                    now=filter_now,
                    max_age_days=linkedin_max_signal_age_days,
                ):
                    continue
            try:
                body = build_message(
                    situation_type, candidate, criteria, now=filter_now
                )
            except MatchedSignalError:
                if channel == SECOND_CHANNEL:
                    continue
                raise
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

    def deliver_batch(self, batch: SendBatch) -> OutreachSummary:
        """Send a loaded batch (e.g. from ``logs/batch_*.json``)."""
        return self._deliver(batch)

    def _deliver(self, batch: SendBatch) -> OutreachSummary:
        if sends_halted():
            return OutreachSummary(skipped=len(batch.messages))

        sent = 0
        suppressed = 0
        skipped = 0
        bounced = 0
        for message in batch.messages:
            if sends_halted():
                skipped += 1
                continue
            if self.suppression.is_suppressed(message.candidate_id):
                suppressed += 1
                continue
            if self.per_run_send_cap is not None and self._sent_this_run >= self.per_run_send_cap:
                skipped += 1
                continue
            if not self.throttle.allow(message.channel):
                skipped += 1
                continue
            try:
                provider_id = self.transport.send(
                    message.channel,
                    message.recipient,
                    message.body,
                    candidate_id=message.candidate_id,
                )
            except Exception:
                self.tracker.record_bounced(
                    message.candidate_id,
                    template_version=message.template_version,
                )
                bounced += 1
                continue
            self.suppression.mark_contacted(message.candidate_id)
            self.throttle.record(message.channel)
            self.tracker.record_sent(
                message.candidate_id,
                template_version=message.template_version,
                provider_message_id=provider_id,
            )
            if self.store is not None:
                self.store.record_send(
                    candidate_id=message.candidate_id,
                    run_id=self.run_id,
                    channel=message.channel,
                    template_version=message.template_version,
                    status="sent",
                )
            self._sent_this_run += 1
            sent += 1
        return OutreachSummary(
            sent=sent,
            replied=0,
            bounced=bounced,
            suppressed=suppressed,
            skipped=skipped,
        )