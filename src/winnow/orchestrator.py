"""Run orchestration: spend cap, audit, pipeline wiring."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from winnow.budget import DEFAULT_SPEND_LOG, SpendTracker
from winnow.criteria.builder import build_criteria, parse_situation
from winnow.enrich import enrich
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
    audit_log_path: str | Path = "logs/runs.jsonl"
    spend_log_path: str | Path = DEFAULT_SPEND_LOG
    search_queries: tuple[str, ...] = ()
    search_limit: int = 50
    enrich_limit: int = 10
    outreach_batch_size: int = 25
    manual_approve: bool = False
    suppressed_candidate_ids: frozenset[str] = field(default_factory=frozenset)
    filter_now: datetime | None = None
    dry_run: bool = False
    daily_cap: int = 50


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
    assert isinstance(item, Candidate)
    return normalize(_candidate_to_raw(item), source_name)


def _collect_free(
    adapters: Sequence[SourceAdapter],
    queries: list[str],
    limit: int,
) -> list[Candidate]:
    collected: list[Candidate] = []
    remaining = max(0, limit)
    for adapter in adapters:
        if adapter.cost_per_call > 0 or remaining <= 0:
            continue
        for item in adapter.search(queries, remaining):
            collected.append(_normalize_item(item, adapter.name))
            remaining -= 1
            if remaining <= 0:
                break
        if remaining <= 0:
            break
    return collected


def _append_audit(path: Path, entry: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, default=str) + "\n")


def run(situation_input: dict, config: RunConfig | None = None) -> RunResult:
    """Execute the Winnow pipeline end-to-end."""
    cfg = config or RunConfig()
    budget = SpendTracker(
        cfg.max_spend_per_run,
        cfg.max_spend_per_month,
        spend_log_path=Path(cfg.spend_log_path),
    )

    situation = parse_situation(situation_input)
    criteria, reachability, template_name = build_criteria(situation)
    criteria_names = tuple(c.name for c in criteria)

    adapters = route(situation, criteria)
    sources = tuple(a.name for a in adapters)

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

    enriched_rows: list[Candidate] = []
    backlog_count = 0
    enriched_count = 0
    enrich_noise = 0
    paid_search_calls = 0

    if possible and not cfg.dry_run:
        enriched_rows, backlog_count, enrich_noise, paid_search_calls = enrich(
            list(possible),
            adapters,
            criteria,
            reachability,
            budget,
            queries=queries,
            enrich_limit=cfg.enrich_limit,
            now=cfg.filter_now,
        )
    elif possible and cfg.dry_run and any(a.cost_per_call > 0 for a in adapters):
        backlog_count = len(possible)

    if enriched_rows:
        enriched_count = len(enriched_rows)
        merged, _ = dedupe([*possible, *enriched_rows])
        possible, extra_noise = apply_filter(
            merged,
            criteria,
            reachability,
            now=cfg.filter_now,
        )
        noise_dropped += extra_noise + enrich_noise

    throttle_caps = {
        "email": cfg.daily_cap,
        "linkedin": cfg.daily_cap,
        "dm": cfg.daily_cap,
    }
    outreach = run_outreach(
        possible,
        situation_type=template_name,
        criteria=criteria,
        batch_size=cfg.outreach_batch_size,
        manual_approve=cfg.manual_approve,
        suppressed_ids=cfg.suppressed_candidate_ids,
        throttle_caps=throttle_caps,
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
        "enrich_backlog_count": backlog_count,
        "enriched_count": enriched_count,
        "outreach": asdict(outreach),
        "spend_run": budget.run_spent,
        "spend_total_month": budget.month_spent,
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
        enriched_count=enriched_count,
        backlog_count=backlog_count,
        spend_this_run=budget.run_spent,
    )