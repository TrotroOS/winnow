"""Paid enrichment for POSSIBLE candidates inside a spend budget."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import TypeAlias

from winnow.budget import SpendCapExceeded, SpendTracker
from winnow.filter import evaluate, reachable
from winnow.models import Candidate, Criteria
from winnow.normalize import normalize
from winnow.sources.adapter import SourceAdapter

ReachabilityFn = Callable[[Candidate], bool]
EnrichFn: TypeAlias = Callable[
    [Candidate, SourceAdapter, list[str], int],
    Sequence[Candidate | dict[str, object]],
]


def assert_possible(
    candidates: Sequence[Candidate],
    criteria: Sequence[Criteria],
    reachability: ReachabilityFn,
    *,
    now: datetime | None = None,
) -> None:
    """Raise if any row is not reachable or fails a criterion predicate."""
    for candidate in candidates:
        if not reachability(candidate):
            msg = f"candidate {candidate.id!r} failed reachability gate"
            raise ValueError(msg)
        if not evaluate(candidate, criteria, now=now):
            msg = f"candidate {candidate.id!r} is not POSSIBLE"
            raise ValueError(msg)


def _paid_adapters(adapters: Sequence[SourceAdapter]) -> list[SourceAdapter]:
    paid = [a for a in adapters if float(a.cost_per_call) > 0]
    return sorted(paid, key=lambda a: (float(a.cost_per_call), a.name))


def _normalize_row(item: Candidate | dict[str, object], source: str) -> Candidate:
    if isinstance(item, Candidate):
        return item
    return normalize(item, source)


def _default_enrich_fn(
    candidate: Candidate,
    adapter: SourceAdapter,
    queries: list[str],
    limit: int,
) -> Sequence[Candidate | dict[str, object]]:
    del candidate
    return adapter.search(queries, limit)


def enrich(
    possible: list[Candidate],
    adapters: Sequence[SourceAdapter],
    criteria: Sequence[Criteria],
    reachability: ReachabilityFn,
    budget: SpendTracker,
    *,
    queries: list[str] | None = None,
    enrich_limit: int = 10,
    enrich_fn: EnrichFn | None = None,
    now: datetime | None = None,
) -> tuple[list[Candidate], int, int, int]:
    """Enrich POSSIBLE rows with cheapest paid adapters first; stop when budget is exhausted.

    Returns ``(enriched, backlog_count, enrich_noise_dropped, paid_calls)``.
    """
    assert_possible(possible, criteria, reachability, now=now)

    paid = _paid_adapters(adapters)
    if not paid or not possible:
        return [], 0, 0, 0

    call = enrich_fn or _default_enrich_fn
    query_list = list(queries or [])
    enriched: list[Candidate] = []
    backlog = 0
    noise = 0
    paid_calls = 0
    primary = paid[0]
    cost = float(primary.cost_per_call)

    for index, candidate in enumerate(possible):
        if not budget.can_afford(cost):
            backlog += len(possible) - index
            break
        try:
            budget.record(cost)
        except SpendCapExceeded:
            backlog += len(possible) - index
            break
        paid_calls += 1

        rows = call(candidate, primary, query_list, enrich_limit)
        for item in rows:
            row = _normalize_row(item, primary.name)
            if not reachability(row):
                noise += 1
                continue
            enriched.append(row)

    return enriched, backlog, noise, paid_calls