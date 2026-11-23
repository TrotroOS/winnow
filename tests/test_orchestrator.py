from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from winnow.criteria.builder import build_criteria, parse_situation
from winnow.filter import reachable
from winnow.models import Candidate, Criteria
from winnow.orchestrator import RunConfig, run
from winnow.sources.registry import clear, register


@dataclass
class CommunityFixture:
    name: str = "mock"
    cost_per_call: float = 0.0

    def search(self, queries: list[str], limit: int) -> list[Candidate]:
        del queries
        if limit <= 0:
            return []
        return [
            Candidate(
                id="community-possible-1",
                name="Casey",
                org="Dev Club",
                role="Member",
                signals={"community_member": "yes", "activity_days": "3"},
                contacts={"email": "casey@devclub.test"},
                source=self.name,
                collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            Candidate(
                id="community-noise-1",
                name="No Contact",
                org="Quiet",
                role="Member",
                signals={"community_member": "yes", "activity_days": "3"},
                contacts={},
                source=self.name,
                collected_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
        ]


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
                signals={"community_member": "yes", "activity_days": "2"},
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


def _community_situation() -> dict:
    return {
        "stage": "seed",
        "product": "Winnow",
        "goal": "grow community",
        "constraint": "time",
        "segment": "devtools",
        "channels": ("email",),
        "situation_type": "community",
    }


def test_spend_cap_halts_enrichment_and_logs_backlog(tmp_path: Path) -> None:
    register(CommunityFixture())
    paid = PaidSpy(cost_per_call=50.0)
    register(paid)

    audit_path = tmp_path / "runs.jsonl"
    result = run(
        _community_situation(),
        RunConfig(
            max_spend_per_run=0.0,
            max_spend_per_month=100.0,
            audit_log_path=audit_path,
            manual_approve=True,
        ),
    )

    assert len(result.possible) >= 1
    assert paid.calls == 0

    entry = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert entry["enrich_backlog_count"] == len(result.possible)
    assert entry["paid_adapter_search_calls"] == 0
    assert entry["spend_run"] == 0.0


def test_empty_possible_zero_paid_adapter_calls(tmp_path: Path) -> None:
    register(CommunityFixture())
    paid = PaidSpy()
    register(paid)

    situation = parse_situation(_community_situation())
    criteria, reachability, template = build_criteria(situation)
    criteria = [
        Criteria(name="impossible", predicate=lambda _: False, cost=0),
        *criteria,
    ]
    audit_path = tmp_path / "runs.jsonl"
    with patch(
        "winnow.orchestrator.build_criteria",
        return_value=(criteria, reachability, template),
    ):
        result = run(
            _community_situation(),
            RunConfig(audit_log_path=audit_path, manual_approve=True),
        )

    assert result.possible == ()
    assert paid.calls == 0
    entry = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert entry["paid_adapter_search_calls"] == 0


def test_audit_entry_records_every_stage(tmp_path: Path) -> None:
    register(CommunityFixture())
    register(PaidSpy())

    audit_path = tmp_path / "runs.jsonl"
    result = run(
        _community_situation(),
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

    assert entry["template"] == "community"
    assert "mock" in entry["sources"]
    assert entry["possible_count"] == len(result.possible)
    assert entry["outreach"]["sent"] == len(result.possible)


def test_manual_approve_skips_outreach_send(tmp_path: Path) -> None:
    register(CommunityFixture())
    register(PaidSpy())

    audit_path = tmp_path / "runs.jsonl"
    result = run(
        _community_situation(),
        RunConfig(
            audit_log_path=audit_path,
            manual_approve=True,
            max_spend_per_run=0.0,
        ),
    )

    assert result.outreach.skipped == len(result.possible)
    assert result.outreach.sent == 0