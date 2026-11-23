"""Run orchestration: spend cap, audit, pipeline wiring.

Bulk filter: ``filter.evaluate`` / ``apply_filter`` are pure per-candidate bool
predicates with no shared mutable state. Candidate rows can be evaluated in parallel
chunks; this module always calls ``apply_filter`` sequentially so NOISE semantics stay
obvious in audit logs. Normalization and filter run on every candidate on every run
even when adapter search hits the same-day cache (cache supplies raw rows only).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from winnow.budget import DEFAULT_SPEND_LOG, SpendTracker
from winnow.store import WinnowStore
from winnow.criteria.builder import build_criteria, parse_situation
from winnow.criteria.generative import load_criteria_version_for_run
from winnow.enrich import enrich
from winnow.filter import apply_filter
from winnow.models import Candidate, OutreachSummary, RunResult
from winnow.normalize import dedupe, normalize
from winnow.outreach.engine import run_outreach
from winnow.router import route
from winnow.sources.adapter import SourceAdapter
from winnow.sources.volume import (
    AdapterVolumeSpec,
    VolumeWrappedAdapter,
    parse_adapter_volume_config,
    wrap_adapters,
)


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
    max_sends_per_run: int = 25
    linkedin_daily_cap: int = 20
    matched_signal_max_age_days: int = 30
    channel_priority: tuple[str, ...] = ()
    store: WinnowStore | None = None
    adapter_volume: dict[str, AdapterVolumeSpec] = field(default_factory=dict)
    adapter_concurrency: int = 1
    volume_day: str = ""
    run_key: str = ""
    criteria_version_id: int | None = None


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


def _volume_day(cfg: RunConfig) -> str:
    if cfg.volume_day:
        return cfg.volume_day
    ref = cfg.filter_now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return ref.astimezone(timezone.utc).date().isoformat()


def _wrap_volume(
    adapters: Sequence[SourceAdapter],
    cfg: RunConfig,
) -> list[VolumeWrappedAdapter | SourceAdapter]:
    if cfg.store is None:
        return list(adapters)
    run_key = cfg.run_key or uuid.uuid4().hex
    cfg.run_key = run_key
    return wrap_adapters(
        adapters,
        store=cfg.store,
        specs=cfg.adapter_volume,
        day=_volume_day(cfg),
        run_key=run_key,
        default_concurrency=cfg.adapter_concurrency,
    )


def _mark_enrich_backlog(
    store: WinnowStore,
    rows: Sequence[Candidate],
    backlog_count: int,
) -> None:
    if backlog_count <= 0:
        return
    for candidate in rows[-backlog_count:]:
        store.save_candidate(candidate, "possible", backlog=True)


def _collect_free(
    adapters: Sequence[SourceAdapter | VolumeWrappedAdapter],
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
    store = cfg.store
    criteria_version_id: int | None = None
    run_db_id: int | None = None

    situation = parse_situation(situation_input)
    if cfg.criteria_version_id is not None:
        if store is None:
            raise ValueError("criteria_version_id requires RunConfig.store")
        criteria, reachability, template_name = load_criteria_version_for_run(
            store, cfg.criteria_version_id
        )
    else:
        criteria, reachability, template_name = build_criteria(situation)
    criteria_names = tuple(c.name for c in criteria)

    adapters = route(situation, criteria)
    volume_adapters = _wrap_volume(adapters, cfg)
    sources = tuple(a.name for a in adapters)

    backlog_rows: list[Candidate] = []
    if store is not None:
        backlog_rows = store.backlog_candidates()

    queries = list(cfg.search_queries) or _default_queries(situation)

    raw_collected = _collect_free(
        [a for a in volume_adapters if a.cost_per_call <= 0],
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

    budget = SpendTracker(
        cfg.max_spend_per_run,
        cfg.max_spend_per_month,
        spend_log_path=Path(cfg.spend_log_path),
        store=store,
        run_id=run_db_id,
    )

    enriched_rows: list[Candidate] = []
    backlog_count = 0
    enriched_count = 0
    enrich_noise = 0
    paid_search_calls = 0

    if not cfg.dry_run:
        if backlog_rows:
            batch, backlog_count, noise_part, paid_part = enrich(
                backlog_rows,
                volume_adapters,
                criteria,
                reachability,
                budget,
                queries=queries,
                enrich_limit=cfg.enrich_limit,
                now=cfg.filter_now,
            )
            enriched_rows.extend(batch)
            enrich_noise += noise_part
            paid_search_calls += paid_part
            if store is not None:
                for row in batch:
                    store.set_backlog(row.id, False)
                if backlog_count > 0:
                    _mark_enrich_backlog(store, backlog_rows, backlog_count)
        if possible:
            batch, backlog_part, noise_part, paid_part = enrich(
                list(possible),
                volume_adapters,
                criteria,
                reachability,
                budget,
                queries=queries,
                enrich_limit=cfg.enrich_limit,
                now=cfg.filter_now,
            )
            enriched_rows.extend(batch)
            backlog_count += backlog_part
            enrich_noise += noise_part
            paid_search_calls += paid_part
            if store is not None and backlog_part > 0:
                _mark_enrich_backlog(store, list(possible), backlog_part)
    elif (possible or backlog_rows) and cfg.dry_run and any(
        a.cost_per_call > 0 for a in adapters
    ):
        backlog_count = len(backlog_rows) + len(possible)

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

    if store is not None:
        criteria_version_id = store.record_criteria_version(
            template_name, criteria_names
        )
        for row in possible:
            store.save_candidate(row, "possible")

    priority = cfg.channel_priority or ("email", "linkedin", "dm")
    throttle_caps = {
        "email": cfg.daily_cap,
        "linkedin": cfg.linkedin_daily_cap,
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
        per_run_send_cap=cfg.max_sends_per_run,
        store=store,
        run_id=run_db_id,
        channel_priority=priority,
        filter_now=cfg.filter_now,
        linkedin_max_signal_age_days=cfg.matched_signal_max_age_days,
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

    if store is not None and criteria_version_id is not None:
        run_db_id = store.record_run(
            criteria_version_id=criteria_version_id,
            situation_type=template_name,
            possible_count=len(possible),
            noise_dropped=noise_dropped,
            spend_run=budget.run_spent,
            enriched_count=enriched_count,
            backlog_count=backlog_count,
            sources=list(sources),
            situation=asdict(situation),
            run_key=cfg.run_key or "",
            outreach=asdict(outreach),
        )

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