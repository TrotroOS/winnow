"""Core datamodels — no scores, ranks, or confidence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Candidate:
    id: str
    name: str
    org: str
    role: str
    signals: dict[str, Any]
    contacts: dict[str, Any]
    source: str
    collected_at: datetime


@dataclass(frozen=True)
class Criterion:
    name: str
    predicate: Callable[[Candidate], bool]


@dataclass
class OutreachCounts:
    sent: int = 0
    replied: int = 0
    bounced: int = 0
    suppressed: int = 0
    skipped: int = 0


@dataclass
class RunResult:
    situation_type: str
    criteria_names: list[str]
    sources: list[str]
    possible: list[Candidate]
    noise_dropped: int
    outreach: OutreachCounts