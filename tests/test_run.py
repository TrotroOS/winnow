from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from winnow.criteria.builder import build_criteria, parse_situation
from winnow.models import Candidate
from winnow.run import execute, main
from winnow.run import write_manual_batch_file
from winnow.sources.registry import clear, register


@dataclass
class ManyFixture:
    name: str = "mock"
    cost_per_call: float = 0.0
    rows: list[Candidate] = field(default_factory=list)
    limits_seen: list[int] = field(default_factory=list)

    def search(self, queries: list[str], limit: int) -> list[Candidate]:
        del queries
        self.limits_seen.append(limit)
        return self.rows[:limit]


@dataclass
class PaidSpy:
    name: str = "paid_spy"
    cost_per_call: float = 50.0
    calls: int = field(default=0, init=False)

    def search(self, queries: list[str], limit: int) -> list[Candidate]:
        del queries, limit
        self.calls += 1
        return []


def _community_yaml(tmp_path: Path) -> Path:
    cfg = {
        "situation": {
            "situation_type": "community",
            "stage": "seed",
            "product": "Winnow",
            "goal": "grow community",
            "constraint": "time",
            "segment": "devtools",
            "channels": ["email"],
        },
        "segment": "devtools",
        "channel": "email",
        "source": "mock",
        "daily_cap": 25,
        "max_spend_per_run": 5,
        "max_spend_per_month": 100,
        "outreach_mode": "manual_approve",
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    return path


def _community_row(i: int) -> Candidate:
    return Candidate(
        id=f"cand-{i}",
        name=f"User {i}",
        org="Dev Club",
        role="Member",
        signals={"community_member": "yes", "activity_days": "2"},
        contacts={"email": f"user{i}@example.com"},
        source="mock",
        collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _register_free_plus_paid(free: ManyFixture, paid: PaidSpy) -> None:
    clear()
    register(free)
    register(paid)


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    clear()
    yield
    clear()


def test_dry_run_zero_paid_calls(tmp_path: Path) -> None:
    config = _community_yaml(tmp_path)
    free = ManyFixture(rows=[_community_row(0)])
    paid = PaidSpy()
    logs = tmp_path / "logs"

    def _reg_sources(_raw: dict) -> None:
        _register_free_plus_paid(free, paid)

    with patch("winnow.run.register_sources_from_config", _reg_sources):
        result, _ = execute(
            config,
            limit=50,
            dry_run=True,
            logs_dir=logs,
        )

    assert paid.calls == 0
    assert result.spend_this_run == 0.0
    assert result.backlog_count == len(result.possible)


def test_limit_enforced_on_collection(tmp_path: Path) -> None:
    config = _community_yaml(tmp_path)
    free = ManyFixture(rows=[_community_row(i) for i in range(20)])
    logs = tmp_path / "logs"

    def _reg(_raw: dict) -> None:
        clear()
        register(free)

    with patch("winnow.run.register_sources_from_config", _reg):
        result, _ = execute(config, limit=3, dry_run=True, logs_dir=logs)

    assert free.limits_seen == [3]
    assert len(result.possible) <= 3


def test_printed_summary_contains_required_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _community_yaml(tmp_path)
    free = ManyFixture(rows=[_community_row(0)])

    def _reg(_raw: dict) -> None:
        clear()
        register(free)

    with patch("winnow.run.register_sources_from_config", _reg):
        code = main(
            ["run", "--config", str(config), "--limit", "5", "--dry-run"],
        )

    assert code == 0
    out = capsys.readouterr().out
    for token in (
        "situation:",
        "template:",
        "criteria_names:",
        "sources_used:",
        "possible:",
        "noise_dropped:",
        "enriched:",
        "backlog:",
        "spend_this_run:",
        "monthly_spend:",
        "batch_path:",
    ):
        assert token in out, out


def test_manual_approve_never_calls_transport(tmp_path: Path) -> None:
    @dataclass
    class SpyTransport:
        calls: int = field(default=0, init=False)

        def send(self, channel, recipient, body, *, candidate_id):
            self.calls += 1
            return "spy"

    config = _community_yaml(tmp_path)
    free = ManyFixture(rows=[_community_row(0)])
    spy = SpyTransport()
    logs = tmp_path / "logs"

    def _reg(_raw: dict) -> None:
        clear()
        register(free)

    with patch("winnow.run.register_sources_from_config", _reg):
        result, _ = execute(config, logs_dir=logs)

    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    situation = parse_situation(raw["situation"])
    criteria, _, template = build_criteria(situation)
    batch_file = logs / "batch_manual.json"
    write_manual_batch_file(
        path=batch_file,
        situation_type=template,
        possible=result.possible,
        criteria=criteria,
        daily_cap=25,
        transport=spy,
    )
    assert spy.calls == 0
    assert result.outreach.sent == 0
    payload = json.loads(batch_file.read_text(encoding="utf-8"))
    assert payload["message_count"] >= 1