"""Audit outreach delivery outcomes by candidate and template version."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

OutreachStatus = Literal["sent", "replied", "bounced"]


@dataclass(frozen=True, slots=True)
class OutreachRecord:
    candidate_id: str
    template_version: str
    status: OutreachStatus


@dataclass
class OutreachTracker:
    records: list[OutreachRecord] = field(default_factory=list)

    def record_sent(self, candidate_id: str, *, template_version: str) -> None:
        self.records.append(
            OutreachRecord(candidate_id, template_version, "sent")
        )

    def record_replied(self, candidate_id: str, *, template_version: str) -> None:
        self.records.append(
            OutreachRecord(candidate_id, template_version, "replied")
        )

    def record_bounced(self, candidate_id: str, *, template_version: str) -> None:
        self.records.append(
            OutreachRecord(candidate_id, template_version, "bounced")
        )

    def sent_ids(self) -> set[str]:
        return {r.candidate_id for r in self.records if r.status == "sent"}