"""Run orchestration: spend cap, audit, pipeline wiring."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from winnow.criteria.builder import build_criteria, parse_situation
from winnow.filter import apply_filter
from winnow.models import Candidate, OutreachSummary, RunResult
from winnow.normalize import dedupe, normalize
from winnow.outreach.engine import run_outreach
from winnow.router import route
from winnow.sources.adapter import SourceAdapter


@dataclass
class RunConfig:
    max_spend_per_run: float = 100.0
    max_spend_per_month: float = 1000.0
    month_spent_so_far: float = 0.0
    audit_log_path: str | Path = "logs/runs.jsonl"
    search_queries: tuple[str, ...] = ()
    search_limit: int = 50
    enrich_limit: int = 10
    outreach_batch_size: int = 25
    manual_approve: bool = False
    suppressed_candidate_ids: frozenset[str] = field(default_factory=frozenset)
    filter_now: datetime | None = None


@dataclass
class CostGovernor:
    max_per_run: float
    max_per_month: float
    month_spent_before: float = 0.0
    run_spent: float = 0.0

    @property
    def total_spent(self) -> float:
        return self.month_spent_before + self.run_spent

    def can_afford(self, amount: float) -> bool:
        if amount < 0:
            return False
        if self.run_spent + amount > self.max_per_run:
            return False
        if self.total_spent + amount > self.max_per_month:
            return False
        return True

    def charge(self, amount: float) -> bool:
        if not self.can_afford(amount):
            return False
        self.run_spent += amount
        return True


def _default_queries(situation) -> list[str]:
    parts = [situation.segment, situation.product, situation.goal.split(":", 1)[-1]]
    return [p.strip() for p in parts if p and p.strip()]


def _candidate_to_raw(candidate: Candidate) -> dict[str, object]:
    return {
        "id": candidate.id,
        "name": candidate.name,
        "org": candidate.org,
        "role": candidate.role,
        "signals": dict(candidate.signals),
        "contacts": dict(candidate.contacts),
        "source": candidate.source,
        "collected_at": candidate.collected_at.isoformat(),
    }


def _normalize_item(item: object, source_name: str) -> Candidate:
    if isinstance(item, dict):
        return normalize(item, source_name)
    return normalize(_candidate_to_raw(item), source_name)


def _collect_free(
    adapters: Sequence[SourceAdapter],
    queries: list[str],
    limit: int,
) -> list[Candidate]:
    collected: list[Candidate] = []
    for adapter in adapters:
        if adapter.cost_per_call > 0:
            continue
        for item in adapter.search(queries, limit):
            collected.append(_normalize_item(item, adapter.name))
    return collected


def _append_audit(path: Path, entry: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, default=str) + "\n")


def run(situation_input: dict, config: RunConfig | None = None) -> RunResult:
    """Execute the Winnow pipeline end-to-end."""
    cfg = config or RunConfig()
    governor = CostGovernor(
        max_per_run=cfg.max_spend_per_run,
        max_per_month=cfg.max_spend_per_month,
        month_spent_before=cfg.month_spent_so_far,
    )

    situation = parse_situation(situation_input)
    criteria, reachability, template_name = build_criteria(situation)
    criteria_names = tuple(c.name for c in criteria)

    adapters = route(situation, criteria)
    sources = tuple(a.name for a in adapters)
    paid = [a for a in adapters if a.cost_per_call > 0]

    queries = list(cfg.search_queries) or _default_queries(situation)

    raw_collected = _collect_free(
        [a for a in adapters if a.cost_per_call <= 0],
        queries,
        cfg.search_limit,
    )
    deduped, dedupe_dropped = dedupe(raw_collected)
    possible, noise_dropped = apply_filter(
        deduped,
        criteria,
        reachability,
        now=cfg.filter_now,
    )

    enrich_backlog = 0
    paid_search_calls = 0

    if possible and paid:
        enriched_rows: list[Candidate] = []
        enrichment_stopped_for_cap = False
        for adapter in paid:
            cost = float(adapter.cost_per_call)
            if not governor.can_afford(cost):
                enrichment_stopped_for_cap = True
                break
            if not governor.charge(cost):
                enrichment_stopped_for_cap = True
                break
            paid_search_calls += 1
            for item in adapter.search(queries, cfg.enrich_limit):
                enriched_rows.append(_normalize_item(item, adapter.name))

        if enrichment_stopped_for_cap or (paid and not enriched_rows and paid_search_calls == 0):
            enrich_backlog = len(possible)
        elif enriched_rows:
            merged, _ = dedupe([*possible, *enriched_rows])
            possible, extra_noise = apply_filter(
                merged,
                criteria,
                reachability,
                now=cfg.filter_now,
            )
            noise_dropped += extra_noise

    outreach = run_outreach(
        possible,
        situation_type=template_name,
        criteria=criteria,
        batch_size=cfg.outreach_batch_size,
        manual_approve=cfg.manual_approve,
        suppressed_ids=cfg.suppressed_candidate_ids,
    )

    possible_ids = tuple(c.id for c in possible)
    audit_entry = {
        "stage": "complete",
        "ts": datetime.now(timezone.utc).isoformat(),
        "situation": asdict(situation),
        "template": template_name,
        "criteria_names": list(criteria_names),
        "sources": list(sources),
        "possible_count": len(possible),
        "possible_ids": list(possible_ids),
        "noise_dropped": noise_dropped,
        "dedupe_dropped": dedupe_dropped,
        "enrich_backlog_count": enrich_backlog,
        "outreach": asdict(outreach),
        "spend_run": governor.run_spent,
        "spend_total_month": governor.total_spent,
        "paid_adapter_search_calls": paid_search_calls,
    }
    _append_audit(Path(cfg.audit_log_path), audit_entry)

    return RunResult(
        situation_type=template_name,
        criteria_names=criteria_names,
        sources=sources,
        possible=tuple(possible),
        noise_dropped=noise_dropped,
        outreach=outreach,
    )