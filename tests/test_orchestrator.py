from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from winnow.filter import reachable
from winnow.models import Candidate, Criteria
from winnow.orchestrator import RunConfig, run
from winnow.sources.mock import MockSource
from winnow.sources.registry import clear, register


@dataclass
class PaidSpy:
    name: str = "paid_spy"
    cost_per_call: float = 50.0
    calls: int = field(default=0, init=False)

    def search(self, queries: list[str], limit: int) -> list[Candidate]:
        self.calls += 1
        return [
            Candidate(
                id="paid-enriched-1",
                name="Enriched",
                org="Paid Org",
                role="VP",
                signals={"tier": "yes"},
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


def _partner_criteria() -> tuple[list[Criteria], callable, str]:
    criteria = [
        Criteria(
            name="tier_yes",
            predicate=lambda c: c.signals.get("tier") == "yes",
            cost=0,
        )
    ]
    return criteria, reachable, "design_partners"


def _situation() -> dict:
    return {
        "stage": "seed",
        "product": "api",
        "situation_type": "design_partners",
        "goal": "find partners",
        "constraint": "budget",
        "segment": "b2b",
        "channels": ("email",),
    }


def test_spend_cap_halts_enrichment_and_logs_backlog(tmp_path: Path) -> None:
    register(MockSource())
    paid = PaidSpy(cost_per_call=50.0)
    register(paid)

    audit_path = tmp_path / "runs.jsonl"
    criteria, reachability, template = _partner_criteria()
    with patch(
        "winnow.orchestrator.build_criteria",
        return_value=(criteria, reachability, template),
    ):
        result = run(
            _situation(),
            RunConfig(
                max_spend_per_run=0.0,
                max_spend_per_month=100.0,
                audit_log_path=audit_path,
            ),
        )

    assert len(result.possible) == 1
    assert paid.calls == 0

    line = audit_path.read_text(encoding="utf-8").strip()
    entry = json.loads(line)
    assert entry["enrich_backlog_count"] == len(result.possible)
    assert entry["paid_adapter_search_calls"] == 0
    assert entry["spend_run"] == 0.0


def test_empty_possible_zero_paid_adapter_calls(tmp_path: Path) -> None:
    register(MockSource())
    paid = PaidSpy()
    register(paid)

    criteria = [Criteria(name="impossible", predicate=lambda _: False, cost=0)]
    audit_path = tmp_path / "runs.jsonl"
    with patch(
        "winnow.orchestrator.build_criteria",
        return_value=(criteria, reachable, "design_partners"),
    ):
        result = run(
            _situation(),
            RunConfig(audit_log_path=audit_path),
        )

    assert result.possible == ()
    assert paid.calls == 0
    entry = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert entry["paid_adapter_search_calls"] == 0


def test_audit_entry_records_every_stage(tmp_path: Path) -> None:
    register(MockSource())
    paid = PaidSpy()
    register(paid)

    audit_path = tmp_path / "runs.jsonl"
    criteria, reachability, template = _partner_criteria()
    with patch(
        "winnow.orchestrator.build_criteria",
        return_value=(criteria, reachability, template),
    ):
        run(
            _situation(),
            RunConfig(
                max_spend_per_run=100.0,
                audit_log_path=audit_path,
                manual_approve=False,
            ),
        )

    entry = json.loads(audit_path.read_text(encoding="utf-8").strip())
    for key in (
        "situation",
        "template",
        "criteria_names",
        "sources",
        "possible_count",
        "possible_ids",
        "noise_dropped",
        "outreach",
        "spend_run",
        "spend_total_month",
        "enrich_backlog_count",
        "paid_adapter_search_calls",
    ):
        assert key in entry, f"missing audit field {key!r}"

    assert entry["template"] == "design_partners"
    assert "mock" in entry["sources"]
    assert "tier_yes" in entry["criteria_names"]
    assert entry["outreach"]["sent"] >= 0


def test_manual_approve_skips_outreach_send(tmp_path: Path) -> None:
    register(MockSource())
    register(PaidSpy())

    criteria, reachability, template = _partner_criteria()
    audit_path = tmp_path / "runs.jsonl"
    with patch(
        "winnow.orchestrator.build_criteria",
        return_value=(criteria, reachability, template),
    ):
        result = run(
            _situation(),
            RunConfig(
                audit_log_path=audit_path,
                manual_approve=True,
                max_spend_per_run=0.0,
            ),
        )

    assert result.outreach.skipped == len(result.possible)
    assert result.outreach.sent == 0