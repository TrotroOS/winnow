from __future__ import annotations

from dataclasses import fields

import pytest

from winnow.filter import apply_filter, evaluate, reachable
from winnow.models import Candidate, Criteria


def test_all_pass_becomes_possible(make_candidate):
    c = make_candidate(contacts={"email": "ada@example.com"}, signals={"tier": "yes"})
    criteria = [Criteria(name="has_tier", predicate=lambda x: x.signals.get("tier") == "yes", cost=1)]
    possible, dropped = apply_filter([c], criteria, reachable)
    assert possible == [c]
    assert dropped == 0


def test_one_fail_dropped_and_counted(make_candidate):
    c = make_candidate(contacts={"email": "ada@example.com"})
    criteria = [Criteria(name="fail", predicate=lambda _: False, cost=1)]
    possible, dropped = apply_filter([c], criteria, reachable)
    assert possible == []
    assert dropped == 1


def test_all_pass_unreachable_dropped(make_candidate):
    c = make_candidate(contacts={}, signals={"ok": "1"})
    criteria = [Criteria(name="ok", predicate=lambda _: True, cost=0)]
    possible, dropped = apply_filter([c], criteria, reachable)
    assert possible == []
    assert dropped == 1


def test_empty_criteria_all_reachable_are_possible(make_candidate):
    a = make_candidate(id="a", contacts={"dm": "@ada"})
    b = make_candidate(id="b", contacts={"linkedin": "https://linkedin.com/in/ada"})
    possible, dropped = apply_filter([a, b], [], reachable)
    assert len(possible) == 2
    assert dropped == 0


def test_predicate_order_respects_cost(make_candidate):
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
    c = make_candidate(contacts={"email": "x@y.com"})
    assert evaluate(c, criteria) is True
    assert order == ["cheap", "mid", "expensive"]


def test_short_circuit_on_first_false(make_candidate):
    calls = 0

    def second(_: Candidate) -> bool:
        nonlocal calls
        calls += 1
        return True

    criteria = [
        Criteria(name="fail", predicate=lambda _: False, cost=1),
        Criteria(name="later", predicate=second, cost=2),
    ]
    c = make_candidate()
    assert evaluate(c, criteria) is False
    assert calls == 0


def test_no_scoring_fields_on_output(make_candidate):
    forbidden = {"score", "rank", "priority", "confidence", "fit", "weight"}
    cand_fields = {f.name for f in fields(Candidate)}
    assert forbidden.isdisjoint(cand_fields)

    c = make_candidate(contacts={"email": "a@b.com"})
    possible, _ = apply_filter([c], [], reachable)
    for item in possible:
        assert forbidden.isdisjoint({f.name for f in fields(item)})


def test_reachable_recognizes_linkedin_and_dm(make_candidate):
    assert reachable(make_candidate(contacts={"email": "  "})) is False
    assert reachable(make_candidate(contacts={"linkedin": " https://li "})) is True
    assert reachable(make_candidate(contacts={"dm": "user"})) is True