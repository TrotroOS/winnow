from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from winnow.filter import apply_filter, reachable
from winnow.models import Candidate, Criteria, StartupSituation
from winnow.router import route
from winnow.sources.mock import MockSource
from winnow.sources.registry import clear, register


@dataclass
class PaidSpy:
    """Raises if ``search`` runs before the caller has filtered to POSSIBLE."""

    name: str = "paid_spy"
    cost_per_call: float = 100.0
    allow_search: bool = False
    calls: int = field(default=0, init=False)

    def search(self, queries: list[str], limit: int) -> list[Candidate]:
        if not self.allow_search:
            raise AssertionError(
                "paid adapter search() invoked before caller allowed enrichment"
            )
        self.calls += 1
        return [
            Candidate(
                id="paid-enriched-1",
                name="Enriched",
                org="Paid Org",
                role="VP",
                signals={},
                contacts={"email": "vp@paid.org"},
                source=self.name,
                collected_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            )
        ]


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    clear()
    yield
    clear()


@pytest.fixture
def mock_candidates_dir(tmp_path: Path) -> Path:
    src = Path(__file__).resolve().parent / "fixtures" / "mock_candidates.json"
    shutil.copy(src, tmp_path / "mock_candidates.json")
    return tmp_path


def test_route_orders_adapters_by_cost_ascending() -> None:
    register(MockSource())
    paid = PaidSpy()
    register(paid)

    situation = StartupSituation(
        stage="seed",
        product="api",
        goal="design partners",
        constraint="budget",
        segment="b2b",
    )
    criteria = [Criteria(name="segment_b2b", predicate=lambda c: c.signals.get("segment") == "b2b")]

    ordered = route(situation, criteria)
    costs = [a.cost_per_call for a in ordered]
    assert costs == sorted(costs)
    assert [a.name for a in ordered] == ["mock", "paid_spy"]


def test_filter_runs_before_paid_search_enrichment(mock_candidates_dir: Path) -> None:
    mock = MockSource(fixtures_dir=mock_candidates_dir)
    paid = PaidSpy()
    register(mock)
    register(paid)

    situation = StartupSituation(
        stage="seed",
        product="api",
        goal="partners",
        constraint="low spend",
        segment="b2b",
    )
    criteria = [
        Criteria(
            name="tier_yes",
            predicate=lambda c: c.signals.get("tier") == "yes",
            cost=0,
        )
    ]

    adapters = route(situation, criteria)
    cheap, expensive = adapters[0], adapters[1]

    raw = cheap.search(["b2b founders"], limit=50)
    possible, noise_dropped = apply_filter(raw, criteria, reachable)

    assert noise_dropped == 1
    assert len(possible) == 1
    assert possible[0].id == "mock-possible-1"
    assert paid.calls == 0

    # Enrichment only after filter: caller opts in when POSSIBLE remain.
    paid.allow_search = True
    enriched = expensive.search(["enrich"], limit=1)
    assert paid.calls == 1
    assert enriched[0].source == "paid_spy"


def test_paid_search_not_invoked_when_everything_is_noise(
    mock_candidates_dir: Path,
) -> None:
    mock = MockSource(fixtures_dir=mock_candidates_dir)
    paid = PaidSpy()
    register(mock)
    register(paid)

    situation = StartupSituation(
        stage="seed",
        product="api",
        goal="partners",
        constraint="low spend",
        segment="b2b",
    )
    criteria = [Criteria(name="impossible", predicate=lambda _: False, cost=0)]

    cheap = route(situation, criteria)[0]
    raw = cheap.search(["any"], limit=50)
    possible, noise_dropped = apply_filter(raw, criteria, reachable)

    assert possible == []
    assert noise_dropped == 2
    assert paid.calls == 0