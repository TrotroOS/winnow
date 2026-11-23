from __future__ import annotations

from datetime import datetime, timezone

from winnow.criteria_builder import build_criteria
from winnow.models import Candidate, Situation


def _candidate(**overrides: object) -> Candidate:
    base = dict(
        id="1",
        name="Alex",
        org="Acme",
        role="CTO",
        signals={"sector": "b2b saas", "geography": "ghana"},
        contacts={"email": "a@acme.test"},
        source="fixture",
        collected_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return Candidate(**base)  # type: ignore[arg-type]


def test_builds_role_and_sector_predicates() -> None:
    situation = Situation(
        situation_type="launch",
        sector_hints=("b2b", "saas"),
        role_hints=("cto",),
        geography="Ghana",
        keywords=(),
    )
    criteria = build_criteria(situation)
    names = {c.name for c in criteria}
    assert names == {"has_org", "role_hint_match", "sector_hint_match", "geography_match"}

    ok = _candidate()
    assert all(c.predicate(ok) for c in criteria)

    bad_role = _candidate(role="Intern")
    assert not next(c for c in criteria if c.name == "role_hint_match").predicate(bad_role)


def test_minimal_situation_only_has_org_rule() -> None:
    situation = Situation("unknown", (), (), None, ())
    criteria = build_criteria(situation)
    assert len(criteria) == 1
    assert criteria[0].name == "has_org"