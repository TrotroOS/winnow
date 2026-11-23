from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from winnow.criteria.generative import (
    CriteriaProposal,
    HeuristicCriteriaProposer,
    PredicateSelection,
    ProposalRejected,
    allow_generative,
    materialize_proposal,
    propose_criteria,
    proposal_from_json,
    proposal_to_json,
    store_generative_proposal,
    validate_proposal,
    vocabulary_keys,
    load_criteria_version_for_run,
)
from winnow.filter import apply_filter
from winnow.models import Candidate, StartupSituation
from winnow.orchestrator import RunConfig, run
from winnow.store import WinnowStore
from winnow.sources.mock import MockSource
from winnow.sources.registry import clear, register


@pytest.fixture
def situation() -> StartupSituation:
    return StartupSituation(
        stage="seed",
        product="Widget",
        goal="community: grow users",
        constraint="budget",
        segment="devtools",
    )


@pytest.fixture(autouse=True)
def _clear_generative_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WINNOW_ALLOW_GENERATIVE", raising=False)


def test_allow_generative_off_by_default() -> None:
    assert allow_generative() is False


def test_allow_generative_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WINNOW_ALLOW_GENERATIVE", "1")
    assert allow_generative() is True


def test_vocabulary_matches_predicate_exports() -> None:
    keys = vocabulary_keys()
    assert "has_signal_within" in keys
    assert "org_in_segment" in keys
    assert "score_candidates" not in keys


def test_select_parameterize_materializes_bool_predicate(situation: StartupSituation) -> None:
    proposal = CriteriaProposal(
        selections=(
            PredicateSelection(
                name="in_segment",
                select="org_in_segment",
                parameters={"segment": situation.segment},
                cost=1,
            ),
            PredicateSelection(
                name="recent",
                select="has_signal_within",
                parameters={"days": 30},
                cost=2,
            ),
        )
    )
    criteria = materialize_proposal(proposal)
    assert len(criteria) == 2
    match = Candidate(
        id="x",
        name="A",
        org="devtools co",
        role="Eng",
        signals={"activity_days": "10", "segment": "devtools"},
        contacts={"email": "a@x.test"},
        source="t",
        collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    possible, noise = apply_filter([match], criteria, lambda c: bool(c.contacts.get("email")))
    assert len(possible) == 1
    assert noise == 0


def test_rejects_unknown_select() -> None:
    proposal = CriteriaProposal(
        selections=(
            PredicateSelection(
                name="bad",
                select="not_in_vocabulary",
                parameters={},
            ),
        )
    )
    with pytest.raises(ProposalRejected):
        validate_proposal(proposal)


def test_rejects_score_weight_and_float(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="winnow.criteria.generative")
    proposal = CriteriaProposal(
        selections=(
            PredicateSelection(
                name="weighted",
                select="signal_is_yes",
                parameters={"key": "hiring", "weight": 0.9},
            ),
        )
    )
    with pytest.raises(ProposalRejected):
        validate_proposal(proposal)
    assert any("forbidden key" in r.message for r in caplog.records)

    proposal_float = CriteriaProposal(
        selections=(
            PredicateSelection(
                name="days",
                select="has_signal_within",
                parameters={"days": 30.5},
            ),
        )
    )
    with pytest.raises(ProposalRejected):
        validate_proposal(proposal_float)
    assert any("float value" in r.message for r in caplog.records)


def test_injectable_proposer(monkeypatch: pytest.MonkeyPatch, situation: StartupSituation) -> None:
    monkeypatch.setenv("WINNOW_ALLOW_GENERATIVE", "1")

    class FakeProposer:
        def propose(self, sit: StartupSituation) -> CriteriaProposal:
            return CriteriaProposal(
                selections=(
                    PredicateSelection(
                        name="custom",
                        select="signal_is_yes",
                        parameters={"key": "community_member"},
                    ),
                )
            )

    proposal = propose_criteria(situation, proposer=FakeProposer())
    assert proposal.selections[0].name == "custom"


def test_propose_disabled_without_env(situation: StartupSituation) -> None:
    with pytest.raises(RuntimeError, match="WINNOW_ALLOW_GENERATIVE"):
        propose_criteria(situation)


def test_store_generative_unapproved(tmp_path, situation: StartupSituation, monkeypatch) -> None:
    monkeypatch.setenv("WINNOW_ALLOW_GENERATIVE", "1")
    store = WinnowStore(tmp_path / "w.sqlite")
    vid = store_generative_proposal(store, situation)
    row = store.get_criteria_version(vid)
    assert row is not None
    assert row["generated"] is True
    assert row["approved"] is False
    assert row["proposal_json"]
    roundtrip = proposal_from_json(row["proposal_json"])
    assert roundtrip.selections


def test_load_requires_approval(tmp_path, situation: StartupSituation, monkeypatch) -> None:
    monkeypatch.setenv("WINNOW_ALLOW_GENERATIVE", "1")
    store = WinnowStore(tmp_path / "w.sqlite")
    vid = store_generative_proposal(store, situation)
    with pytest.raises(ValueError, match="not approved"):
        load_criteria_version_for_run(store, vid)


def test_orchestrator_uses_approved_generated(
    tmp_path, situation: StartupSituation, monkeypatch
) -> None:
    monkeypatch.setenv("WINNOW_ALLOW_GENERATIVE", "1")
    store = WinnowStore(tmp_path / "w.sqlite")
    vid = store_generative_proposal(store, situation)
    store.approve_criteria_version(vid)

    clear()
    register(MockSource())
    cfg = RunConfig(
        audit_log_path=tmp_path / "runs.jsonl",
        spend_log_path=tmp_path / "spend.json",
        search_limit=5,
        dry_run=True,
        store=store,
        criteria_version_id=vid,
    )
    result = run(
        {
            "situation_type": "community",
            "stage": situation.stage,
            "product": situation.product,
            "goal": situation.goal,
            "constraint": situation.constraint,
            "segment": situation.segment,
        },
        cfg,
    )
    assert result.situation_type == "generated" or result.criteria_names


def test_heuristic_proposer_roundtrip_json(situation: StartupSituation) -> None:
    proposal = HeuristicCriteriaProposer().propose(situation)
    validate_proposal(proposal)
    raw = proposal_to_json(proposal)
    again = proposal_from_json(raw)
    assert again.selections == proposal.selections