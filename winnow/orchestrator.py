"""Run pipeline with spend-cap enforcement."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from winnow.audit import write_audit_log
from winnow.binary_filter import partition_possible
from winnow.config import WinnowConfig
from winnow.criteria_builder import build_criteria
from winnow.dedupe import dedupe_by_id
from winnow.models import Candidate, OutreachCounts, RunResult
from winnow.normalize import normalize_batch
from winnow.outreach_engine import run_outreach
from winnow.reachability import ReachabilityPredicate, default_reachable
from winnow.situation_parser import parse_situation
from winnow.source_router import fetch_all_ordered

from winnow.adapters.base import SourceAdapter

logger = logging.getLogger(__name__)


@dataclass
class SpendTracker:
    cap_cents: int
    spent_cents: int = 0
    enrichment_backlog: int = 0

    def can_spend(self, cents: int) -> bool:
        if self.cap_cents <= 0:
            return True
        return self.spent_cents + cents <= self.cap_cents

    def record_spend(self, cents: int) -> None:
        self.spent_cents += cents


def _enrich_stub(
    possible: list[Candidate],
    tracker: SpendTracker,
    cost_per_enrichment_cents: int,
) -> list[Candidate]:
    """Placeholder enrichment after binary filter; respects spend cap."""
    enriched: list[Candidate] = []
    for candidate in possible:
        if not tracker.can_spend(cost_per_enrichment_cents):
            tracker.enrichment_backlog += 1
            logger.info(
                "spend cap exhausted; enrichment backlog=%s",
                tracker.enrichment_backlog,
            )
            break
        tracker.record_spend(cost_per_enrichment_cents)
        enriched.append(candidate)
    return enriched


def run_winnow(
    situation: str | dict[str, Any],
    adapters: list[SourceAdapter],
    *,
    config: WinnowConfig | None = None,
    reachable: ReachabilityPredicate | None = None,
    audit_log_path: Path | str | None = None,
    suppressed_ids: set[str] | None = None,
    enrichment_cost_cents: int = 10,
) -> RunResult:
    """Execute the core pipeline through outreach and optional audit log."""
    cfg = config or WinnowConfig.from_env()
    reach = reachable or default_reachable
    tracker = SpendTracker(cap_cents=cfg.spend_cap_cents)

    situation_type = parse_situation(situation)
    criteria = build_criteria(situation_type)
    criteria_names = [c.name for c in criteria]

    all_candidates: list[Candidate] = []
    sources_used: list[str] = []
    for source_name, raw_records in fetch_all_ordered(adapters):
        sources_used.append(source_name)
        all_candidates.extend(normalize_batch(raw_records, source_name))

    deduped = dedupe_by_id(all_candidates)
    possible, noise_dropped = partition_possible(deduped, criteria, reach)

    # Enrichment only after binary filter (stub; no external I/O).
    _ = cfg.enrichment_api_key
    possible_after_enrich = _enrich_stub(possible, tracker, enrichment_cost_cents)
    if tracker.enrichment_backlog:
        logger.info("enrichment_backlog_count=%s", tracker.enrichment_backlog)

    outreach: OutreachCounts = run_outreach(possible_after_enrich, suppressed_ids)

    result = RunResult(
        situation_type=situation_type,
        criteria_names=criteria_names,
        sources=sources_used,
        possible=possible_after_enrich,
        noise_dropped=noise_dropped,
        outreach=outreach,
    )

    if audit_log_path is not None:
        write_audit_log(result, audit_log_path)

    return result