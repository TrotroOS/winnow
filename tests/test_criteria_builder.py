from __future__ import annotations

import inspect
from dataclasses import fields
from datetime import datetime, timezone

import pytest

from winnow.criteria.builder import build_criteria, parse_situation
from winnow.criteria.templates import TEMPLATES
from winnow.filter import apply_filter
from winnow.models import Candidate, Criteria


def _base_data(**overrides: object) -> dict:
    data = {
        "stage": "seed",
        "product": "Acme API",
        "goal": "placeholder",
        "constraint": "time",
        "segment": "devtools",
        "channels": ("email",),
    }
    data.update(overrides)
    return data


def _matching_candidate(template: str, *, segment: str = "devtools") -> dict:
    email = {"email": "reach@example.com"}
    if template == "design_partners":
        return dict(
            org="DevTools Co",
            role="VP Product",
            signals={
                "design_partner_open": "yes",
                "segment": segment,
                "activity_days": "14",
            },
            contacts=email,
        )
    if template == "first_revenue":
        return dict(
            org="Buyer Inc",
            role="CEO",
            signals={"revenue_ready": "yes", "activity_days": "10"},
            contacts=email,
        )
    if template == "distribution_partners":
        return dict(
            org="Partner Hub",
            role="Alliances",
            signals={
                "partner_page": "yes",
                "complementary_product": "Acme API",
                "segment": segment,
            },
            contacts=email,
        )
    if template == "investors":
        return dict(
            org="Seed VC",
            role="General Partner",
            signals={"invests_in": "devtools", "activity_days": "45"},
            contacts=email,
        )
    if template == "hires":
        return dict(
            org="Hiring Co",
            role="Recruiter",
            signals={
                "hiring": "yes",
                "open_roles": "engineer, Acme API",
                "segment": segment,
            },
            contacts=email,
        )
    if template == "community":
        return dict(
            org="Community Org",
            role="Member",
            signals={"community_member": "yes", "activity_days": "3"},
            contacts=email,
        )
    if template == "segment_expansion":
        return dict(
            org="Enterprise Co",
            role="CEO",
            signals={
                "segment_expansion_open": "yes",
                "segment": segment,
                "activity_days": "14",
            },
            contacts=email,
        )
    raise KeyError(template)


def _non_matching_candidate(template: str) -> dict:
    return dict(
        org="Noise LLC",
        role="Intern",
        signals={},
        contacts={"email": "noise@example.com"},
    )


@pytest.mark.parametrize("template_name", sorted(TEMPLATES))
def test_template_matching_candidate_passes_filter(
    make_candidate, template_name: str
) -> None:
    segment = "enterprise" if template_name == "segment_expansion" else "devtools"
    data = _base_data(situation_type=template_name, segment=segment)
    situation = parse_situation(data)
    criteria, reachability, name = build_criteria(situation)
    assert name == template_name

    good = make_candidate(**_matching_candidate(template_name, segment=segment))
    possible, dropped = apply_filter([good], criteria, reachability)
    assert possible == [good]
    assert dropped == 0


@pytest.mark.parametrize("template_name", sorted(TEMPLATES))
def test_template_non_matching_candidate_dropped(
    make_candidate, template_name: str
) -> None:
    segment = "enterprise" if template_name == "segment_expansion" else "devtools"
    data = _base_data(situation_type=template_name, segment=segment)
    situation = parse_situation(data)
    criteria, reachability, _ = build_criteria(situation)

    bad = make_candidate(**_non_matching_candidate(template_name))
    possible, dropped = apply_filter([bad], criteria, reachability)
    assert possible == []
    assert dropped == 1


def test_criteria_are_callables_only_no_goodness_fields() -> None:
    situation = parse_situation(
        _base_data(situation_type="community", goal="grow community")
    )
    criteria, _, _ = build_criteria(situation)
    forbidden = frozenset(
        {"quality", "score", "priority", "rank", "confidence", "fit", "weight"}
    )
    for item in criteria:
        assert isinstance(item, Criteria)
        field_names = {f.name for f in fields(item)}
        assert field_names <= {"name", "predicate", "cost"}
        assert forbidden.isdisjoint(field_names)
        assert callable(item.predicate)
        params = inspect.signature(item.predicate).parameters
        assert "score" not in params and "weight" not in params


def test_unknown_situation_raises_value_error() -> None:
    situation = parse_situation(
        {
            "stage": "seed",
            "product": "X",
            "goal": "do something vague",
            "constraint": "",
            "segment": "other",
            "channels": (),
        }
    )
    with pytest.raises(ValueError, match="Unknown situation"):
        build_criteria(situation)


def test_keyword_inference_single_match() -> None:
    situation = parse_situation(_base_data(goal="find our first revenue customer"))
    _, _, name = build_criteria(situation)
    assert name == "first_revenue"