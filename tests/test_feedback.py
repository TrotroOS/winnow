from __future__ import annotations

import inspect
from dataclasses import fields
from typing import get_type_hints

import pytest

from winnow.criteria.templates import TEMPLATES, build_from_template
from winnow.feedback import (
    POSSIBLE_COUNT_TOO_LARGE,
    POSSIBLE_COUNT_TOO_SMALL,
    TemplateStats,
    ingest_replies,
    tune,
)
from winnow.models import Candidate, Criteria, StartupSituation
from winnow.outreach.tracker import OutreachRecord, OutreachTracker


FORBIDDEN = frozenset(
    {"quality", "score", "priority", "rank", "confidence", "fit", "weight", "threshold"}
)


@pytest.fixture
def sample_tracker() -> dict[str, OutreachTracker]:
    community = OutreachTracker()
    for cid in ("a", "b", "c", "d"):
        community.record_sent(cid, template_version="2026.11")
    community.record_replied("a", template_version="2026.11")
    community.record_replied("b", template_version="2026.11")
    return {"community": community}


def test_ingest_replies_aggregates_rate(sample_tracker) -> None:
    stats = ingest_replies(sample_tracker)
    assert set(stats) == {"community"}
    row = stats["community"]
    assert row.sent == 4
    assert row.replied == 2
    assert row.rate == pytest.approx(0.5)


def test_ingest_replies_zero_sent_zero_rate() -> None:
    stats = ingest_replies({"empty": {"sent": 0, "replied": 0}})
    assert stats["empty"].rate == 0.0


def test_tune_too_large_suggests_tighten() -> None:
    names = ("design_partner_open", "org_in_segment", "recent_activity")
    stats = TemplateStats(sent=10, replied=2, rate=0.2)
    text = tune(
        "design_partners",
        stats,
        possible_count=POSSIBLE_COUNT_TOO_LARGE + 10,
        predicate_names=names,
    )
    assert isinstance(text, str)
    assert text.startswith("SUGGESTION")
    assert "Tighten" in text
    assert "design_partner_open" in text
    assert str(POSSIBLE_COUNT_TOO_LARGE) in text


def test_tune_too_small_suggests_loosen() -> None:
    names = ("design_partner_open", "org_in_segment", "recent_activity")
    stats = TemplateStats(sent=5, replied=1, rate=0.2)
    text = tune(
        "design_partners",
        stats,
        possible_count=POSSIBLE_COUNT_TOO_SMALL - 1,
        predicate_names=names,
    )
    assert isinstance(text, str)
    assert "Loosen" in text
    assert "recent_activity" in text
    assert str(POSSIBLE_COUNT_TOO_SMALL) in text


def test_tune_in_range_no_mutation_path(sample_tracker) -> None:
    stats = ingest_replies(sample_tracker)["community"]
    text = tune("community", stats, possible_count=10)
    assert "within operator bounds" in text
    assert isinstance(text, str)


def test_no_numeric_goodness_fields_on_models() -> None:
    assert FORBIDDEN.isdisjoint({f.name for f in fields(Candidate)})
    assert FORBIDDEN.isdisjoint({f.name for f in fields(Criteria)})


def test_ingest_and_tune_never_add_score_fields_to_models(sample_tracker) -> None:
    situation = StartupSituation(
        stage="seed",
        product="p",
        goal="x",
        constraint="c",
        segment="devtools",
    )
    for template_name in TEMPLATES:
        criteria, _reach = build_from_template(template_name, situation)
        stats = ingest_replies(sample_tracker)
        tune(
            template_name,
            stats.get("community", TemplateStats(0, 0, 0.0)),
            possible_count=100,
            predicate_names=tuple(c.name for c in criteria),
        )
    assert FORBIDDEN.isdisjoint({f.name for f in fields(Candidate)})
    assert FORBIDDEN.isdisjoint({f.name for f in fields(Criteria)})
    hints = get_type_hints(tune)
    assert hints.get("return") is str
    sig = inspect.signature(tune)
    assert sig.return_annotation in (str, "str")


def test_ingest_accepts_record_list() -> None:
    records = [
        OutreachRecord("1", "v1", "sent"),
        OutreachRecord("2", "v1", "sent"),
        OutreachRecord("1", "v1", "replied"),
    ]
    stats = ingest_replies({"tpl": records})
    assert stats["tpl"].sent == 2
    assert stats["tpl"].replied == 1
    assert stats["tpl"].rate == pytest.approx(0.5)