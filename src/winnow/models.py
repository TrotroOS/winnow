from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Candidate:
    id: str
    name: str
    org: str
    role: str
    signals: dict[str, str]
    contacts: dict[str, str]
    source: str
    collected_at: datetime


@dataclass(frozen=True, slots=True)
class Criteria:
    name: str
    predicate: Callable[[Candidate], bool]
    cost: int = 0  # execution order only; never used for weighting or scores


@dataclass(frozen=True, slots=True)
class StartupSituation:
    stage: str
    product: str
    goal: str
    constraint: str
    segment: str
    channels: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OutreachSummary:
    sent: int = 0
    replied: int = 0
    bounced: int = 0
    suppressed: int = 0
    skipped: int = 0


@dataclass(frozen=True, slots=True)
class RunResult:
    situation_type: str
    criteria_names: tuple[str, ...]
    sources: tuple[str, ...]
    possible: tuple[Candidate, ...]
    noise_dropped: int
    outreach: OutreachSummary
    enriched_count: int = 0
    backlog_count: int = 0
    spend_this_run: float = 0.0