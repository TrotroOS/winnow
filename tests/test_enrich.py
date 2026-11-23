from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from winnow.budget import SpendTracker
from winnow.enrich import assert_possible, enrich
from winnow.filter import apply_filter, reachable
from winnow.models import Candidate, Criteria


def _possible(**overrides: object) -> Candidate:
    base = dict(
        id="p1",
        name="Ada",
        org="Org",
        role="CTO",
        signals={"tier": "yes"},
        contacts={"email": "ada@org.test"},
        source="fixture",
        collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return Candidate(**base)  # type: ignore[arg-type]


def _criteria() -> list[Criteria]:
    return [
        Criteria(
            name="tier_yes",
            predicate=lambda c: c.signals.get("tier") == "yes",
            cost=0,
        )
    ]


@dataclass
class PossibleOnlySpy:
    name: str = "paid"
    cost_per_call: float = 10.0
    calls: list[str] = field(default_factory=list)

    def search(self, queries: list[str], limit: int) -> list[dict[str, object]]:
        raise AssertionError(
            "paid search() must not run without a POSSIBLE candidate context"
        )


def test_assert_possible_rejects_noise_before_paid_calls() -> None:
    criteria = _criteria()
    noise = _possible(id="noise", contacts={})
    with pytest.raises(ValueError, match="reachability"):
        assert_possible([noise], criteria, reachable)


def test_spy_enrich_fn_only_called_with_possible() -> None:
    spy = PossibleOnlySpy()
    criteria = _criteria()
    good = _possible(id="ok1")
    noise = _possible(id="bad", contacts={})

    def enrich_fn(
        candidate: Candidate,
        adapter: PossibleOnlySpy,
        queries: list[str],
        limit: int,
    ) -> list[dict[str, object]]:
        del queries, limit
        if not reachable(candidate):
            raise AssertionError("adapter called with candidate not POSSIBLE")
        spy.calls.append(candidate.id)
        return [
            {
                "id": f"enriched-{candidate.id}",
                "name": candidate.name,
                "org": candidate.org,
                "role": candidate.role,
                "signals": dict(candidate.signals),
                "contacts": {"email": f"new+{candidate.id}@test"},
                "collected_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
            }
        ]

    budget = SpendTracker(max_spend_per_run=100.0, max_spend_per_month=1000.0)

    with pytest.raises(ValueError):
        enrich(
            [noise],
            [spy],
            criteria,
            reachable,
            budget,
            enrich_fn=enrich_fn,
        )
    assert spy.calls == []

    enriched, backlog, noise_dropped, paid_calls = enrich(
        [good],
        [spy],
        criteria,
        reachable,
        budget,
        enrich_fn=enrich_fn,
    )
    assert spy.calls == ["ok1"]
    assert paid_calls == 1
    assert backlog == 0
    assert noise_dropped == 0
    assert len(enriched) == 1


def test_cap_mid_batch_stops_without_overspend(tmp_path) -> None:
    spend_path = tmp_path / "spend.json"

    @dataclass
    class CheapPaid:
        name: str = "paid"
        cost_per_call: float = 40.0
        n_calls: int = field(default=0, init=False)

        def search(self, queries: list[str], limit: int) -> list[dict[str, object]]:
            self.n_calls += 1
            return []

    paid = CheapPaid()
    criteria = _criteria()
    rows = [_possible(id=f"p{i}") for i in range(3)]
    budget = SpendTracker(
        max_spend_per_run=75.0,
        max_spend_per_month=1000.0,
        spend_log_path=spend_path,
    )

    enriched, backlog, _, paid_calls = enrich(
        rows,
        [paid],
        criteria,
        reachable,
        budget,
    )

    assert enriched == []
    assert paid.n_calls == 1
    assert paid_calls == 1
    assert budget.run_spent == pytest.approx(40.0)
    assert backlog == 2
    assert budget.run_spent <= budget.max_spend_per_run


def test_unreachable_after_enrichment_counted_as_noise() -> None:
    @dataclass
    class Paid:
        name: str = "paid"
        cost_per_call: float = 5.0

        def search(self, queries: list[str], limit: int) -> list[dict[str, object]]:
            return [
                {
                    "id": "ghost",
                    "name": "Ghost",
                    "org": "x",
                    "role": "r",
                    "signals": {"tier": "yes"},
                    "contacts": {},
                    "collected_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                }
            ]

    criteria = _criteria()
    budget = SpendTracker(50.0, 500.0)
    enriched, backlog, noise_dropped, _ = enrich(
        [_possible()],
        [Paid()],
        criteria,
        reachable,
        budget,
    )
    assert enriched == []
    assert backlog == 0
    assert noise_dropped == 1


def test_filter_integration_possible_only_input() -> None:
    criteria = _criteria()
    candidate = _possible()
    possible, dropped = apply_filter([candidate], criteria, reachable)
    assert dropped == 0
    assert len(possible) == 1