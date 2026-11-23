from __future__ import annotations

from dataclasses import fields
from typing import Any

from winnow.filter import apply_filter, evaluate, reachable
from winnow.models import Candidate, Criteria


def test_all_pass_becomes_possible(make_candidate) -> None:
    candidate = make_candidate(
        contacts={"email": "ada@example.org"},
        signals={"tier": "yes"},
    )
    criteria = [
        Criteria(
            name="has_tier",
            predicate=lambda c: c.signals.get("tier") == "yes",
            cost=1,
        )
    ]
    possible, dropped = apply_filter([candidate], criteria, reachable)
    assert possible == [candidate]
    assert dropped == 0


def test_one_fail_dropped_and_counted(make_candidate) -> None:
    candidate = make_candidate(contacts={"email": "ada@example.org"})
    criteria = [
        Criteria(name="fail", predicate=lambda _: False, cost=0),
        Criteria(name="never_runs", predicate=lambda _: True, cost=1),
    ]
    possible, dropped = apply_filter([candidate], criteria, reachable)
    assert possible == []
    assert dropped == 1


def test_unreachable_dropped_and_counted(make_candidate) -> None:
    candidate = make_candidate(contacts={}, signals={"ok": "1"})
    criteria = [Criteria(name="always", predicate=lambda _: True, cost=0)]
    possible, dropped = apply_filter([candidate], criteria, reachable)
    assert possible == []
    assert dropped == 1


def test_empty_criteria_all_reachable_are_possible(make_candidate) -> None:
    a = make_candidate(id="a", contacts={"dm": "@ada"})
    b = make_candidate(id="b", contacts={"linkedin": "https://linkedin.com/in/ada"})
    possible, dropped = apply_filter([a, b], [], reachable)
    assert len(possible) == 2
    assert dropped == 0


def test_short_circuit_skips_remaining_predicates(make_candidate) -> None:
    call_order: list[str] = []

    def pred(name: str, result: bool):
        def _inner(_: Candidate) -> bool:
            call_order.append(name)
            return result

        return _inner

    candidate = make_candidate(contacts={"email": "x@y.z"})
    criteria = [
        Criteria(name="cheap_fail", predicate=pred("cheap", False), cost=1),
        Criteria(name="expensive", predicate=pred("expensive", True), cost=100),
    ]
    assert evaluate(candidate, criteria) is False
    assert call_order == ["cheap"]


def test_predicate_order_respects_cost(make_candidate) -> None:
    order: list[str] = []

    def mk(name: str):
        def pred(_: Candidate) -> bool:
            order.append(name)
            return True

        return pred

    criteria = [
        Criteria(name="expensive", predicate=mk("expensive"), cost=10),
        Criteria(name="cheap", predicate=mk("cheap"), cost=1),
        Criteria(name="mid", predicate=mk("mid"), cost=5),
    ]
    candidate = make_candidate(contacts={"email": "x@y.com"})
    assert evaluate(candidate, criteria) is True
    assert order == ["cheap", "mid", "expensive"]


def test_short_circuit_skips_remaining_predicates(make_candidate) -> None:
    calls = 0

    def second(_: Candidate) -> bool:
        nonlocal calls
        calls += 1
        return True

    criteria = [
        Criteria(name="fail", predicate=lambda _: False, cost=1),
        Criteria(name="later", predicate=second, cost=2),
    ]
    candidate = make_candidate()
    assert evaluate(candidate, criteria) is False
    assert calls == 0


def test_reachability_keys_email_linkedin_dm(make_candidate) -> None:
    assert reachable(make_candidate(contacts={"email": "a@b.co"}))
    assert reachable(make_candidate(contacts={"linkedin": "https://linkedin.com/in/x"}))
    assert reachable(make_candidate(contacts={"dm": "@handle"}))
    assert not reachable(make_candidate(contacts={"email": "   "}))
    assert not reachable(make_candidate(contacts={"phone": "+15551234567"}))
    assert not reachable(make_candidate(contacts={}))


def test_no_scoring_or_ranking_on_output(make_candidate) -> None:
    forbidden = frozenset(
        {"quality", "score", "priority", "rank", "confidence", "fit", "weight"}
    )
    assert forbidden.isdisjoint({f.name for f in fields(Candidate)})

    candidate = make_candidate(contacts={"email": "a@b.com"})
    possible, _ = apply_filter([candidate], [], reachable)
    for item in possible:
        assert forbidden.isdisjoint({f.name for f in fields(item)})
        for name, value in _iter_public_attrs(item):
            assert name.lower() not in forbidden
            if isinstance(value, dict):
                for k in value:
                    assert k.lower() not in forbidden


def test_reachability_keys_email_linkedin_dm(make_candidate) -> None:
    assert reachable(make_candidate(contacts={"email": "a@b.co"}))
    assert reachable(make_candidate(contacts={"linkedin": " https://li "}))
    assert reachable(make_candidate(contacts={"dm": "user"}))
    assert not reachable(make_candidate(contacts={"email": "   "}))
    assert not reachable(make_candidate(contacts={"phone": "+15551234567"}))
    assert not reachable(make_candidate(contacts={}))


def _iter_public_attrs(obj: Any) -> list[tuple[str, Any]]:
    return [(f.name, getattr(obj, f.name)) for f in fields(obj)]