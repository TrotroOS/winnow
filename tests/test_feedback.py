from __future__ import annotations

import inspect
import json
from dataclasses import fields
from pathlib import Path
from typing import get_type_hints

import pytest

from winnow.criteria.templates import TEMPLATES, build_from_template
from winnow.feedback import (
    LIST_SIZE_DAILY_CAP_MULTIPLIER,
    POSSIBLE_COUNT_TOO_SMALL,
    TemplateStats,
    append_feedback_log,
    emit_suggestions,
    ingest,
    suggest,
)
from winnow.models import Candidate, Criteria, StartupSituation
from winnow.outreach.tracker import OutreachTracker

FORBIDDEN = frozenset(
    {"quality", "score", "priority", "rank", "confidence", "fit", "weight", "threshold"}
)


@pytest.fixture
def sample_tracker() -> OutreachTracker:
    tracker = OutreachTracker()
    for cid in ("a", "b", "c", "d"):
        tracker.record_sent(cid, template_version="community")
    tracker.record_replied("a", template_version="community")
    tracker.record_replied("b", template_version="community")
    tracker.record_bounced("c", template_version="community")
    tracker.record_opt_out("d", template_version="community")
    return tracker


def test_ingest_aggregates_per_template_bucket(sample_tracker) -> None:
    stats = ingest(sample_tracker)
    assert set(stats) == {"community"}
    row = stats["community"]
    assert row.sent == 4
    assert row.replied == 2
    assert row.bounced == 1
    assert row.opt_out == 1
    assert row.reply_rate == pytest.approx(0.5)
    assert row.bounce_rate == pytest.approx(0.25)


def test_suggest_too_large_tightens_predicate() -> None:
    daily_cap = 25
    stats = TemplateStats(sent=10, replied=1)
    text = suggest(
        "community",
        stats,
        possible_count=daily_cap * LIST_SIZE_DAILY_CAP_MULTIPLIER + 5,
        daily_cap=daily_cap,
        predicate_names=("community_member", "recent_activity"),
    )
    assert "Tighten predicate 'community_member'" in text
    assert str(daily_cap * LIST_SIZE_DAILY_CAP_MULTIPLIER) in text


def test_suggest_too_small_loosens_predicate() -> None:
    stats = TemplateStats(sent=5, replied=1)
    text = suggest(
        "community",
        stats,
        possible_count=POSSIBLE_COUNT_TOO_SMALL - 1,
        daily_cap=25,
        predicate_names=("community_member", "recent_activity"),
    )
    assert "Loosen predicate 'recent_activity'" in text
    assert str(POSSIBLE_COUNT_TOO_SMALL) in text


def test_suggest_high_bounce_tightens_reachability() -> None:
    stats = TemplateStats(sent=100, replied=10, bounced=5)
    text = suggest(
        "community",
        stats,
        possible_count=10,
        daily_cap=25,
        predicate_names=("community_member",),
    )
    assert "bounce rate" in text
    assert "tighten reachability" in text.lower()


def test_suggest_low_reply_rate_reviews_matched_signal() -> None:
    stats = TemplateStats(sent=100, replied=1, bounced=0)
    text = suggest(
        "community",
        stats,
        possible_count=10,
        daily_cap=25,
        matched_signal_hint="community_member",
    )
    assert "reply rate" in text
    assert "community_member" in text


def test_no_numeric_goodness_fields_on_models() -> None:
    assert FORBIDDEN.isdisjoint({f.name for f in fields(Candidate)})
    assert FORBIDDEN.isdisjoint({f.name for f in fields(Criteria)})


def test_suggest_never_mutates_model_fields(sample_tracker) -> None:
    situation = StartupSituation(
        stage="seed",
        product="p",
        goal="x",
        constraint="c",
        segment="devtools",
    )
    for template_name in TEMPLATES:
        criteria, _reach = build_from_template(template_name, situation)
        row = ingest(sample_tracker).get("community", TemplateStats(0, 0))
        suggest(
            template_name,
            row,
            possible_count=200,
            daily_cap=25,
            predicate_names=tuple(c.name for c in criteria),
            matched_signal_hint=criteria[0].name if criteria else "matched_signal",
        )
    assert FORBIDDEN.isdisjoint({f.name for f in fields(Candidate)})
    assert FORBIDDEN.isdisjoint({f.name for f in fields(Criteria)})
    hints = get_type_hints(suggest)
    assert hints.get("return") is str
    assert inspect.signature(suggest).return_annotation in (str, "str")


def test_feedback_jsonl_append_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log_path = tmp_path / "feedback.jsonl"
    append_feedback_log(log_path, {"a": 1})
    append_feedback_log(log_path, {"b": 2})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}

    emit_suggestions("line-3", log_path=log_path, template_name="community")
    out = capsys.readouterr().out.strip()
    assert out == "line-3"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    last = json.loads(lines[2])
    assert last["suggestion"] == "line-3"
    assert last["template"] == "community"