from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from freezegun import freeze_time

from winnow.models import Candidate
from winnow.scheduler import (
    RunLock,
    record_daily_fire,
    scheduled_job,
    should_fire_daily,
)
from winnow.sources.registry import clear, register
from winnow.store import WinnowStore


@dataclass
class ManyFixture:
    name: str = "mock"
    cost_per_call: float = 0.0
    rows: list[Candidate] = field(default_factory=list)

    def search(self, queries: list[str], limit: int) -> list[Candidate]:
        del queries
        return self.rows[:limit]


def _config(tmp_path: Path, **overrides: object) -> Path:
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
        "sources": ["mock"],
        "daily_cap": 25,
        "max_spend_per_run": 5,
        "max_spend_per_month": 100,
        "possible_min": 1,
        "possible_max": 100,
        "daily_run_time": "09:00",
        "timezone": "UTC",
    }
    cfg.update(overrides)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    return path


def _row(i: int) -> Candidate:
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


@freeze_time("2026-11-23 08:59:00+00:00")
def test_should_fire_not_before_run_time(tmp_path: Path) -> None:
    from zoneinfo import ZoneInfo

    from winnow.scheduler import parse_daily_run_time

    state = tmp_path / "scheduler.state.json"
    tz = ZoneInfo("UTC")
    now = datetime.now(timezone.utc)
    assert (
        should_fire_daily(
            now,
            state_path=state,
            run_time=parse_daily_run_time("09:00"),
            tz=tz,
        )
        is False
    )


@freeze_time("2026-11-23 09:00:00+00:00")
def test_fires_once_at_configured_time_not_twice(tmp_path: Path) -> None:
    from zoneinfo import ZoneInfo

    from winnow.scheduler import parse_daily_run_time

    state = tmp_path / "scheduler.state.json"
    tz = ZoneInfo("UTC")
    run_time = parse_daily_run_time("09:00")
    now = datetime.now(timezone.utc)

    assert should_fire_daily(now, state_path=state, run_time=run_time, tz=tz)
    record_daily_fire(state, now, tz)
    assert (
        should_fire_daily(now, state_path=state, run_time=run_time, tz=tz) is False
    )

    with freeze_time("2026-11-24 09:00:00+00:00"):
        next_now = datetime.now(timezone.utc)
        assert should_fire_daily(
            next_now, state_path=state, run_time=run_time, tz=tz
        )


def test_lock_prevents_overlap(tmp_path: Path) -> None:
    lock_path = tmp_path / "winnow.run.lock"
    first = RunLock(lock_path)
    second = RunLock(lock_path)
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()


def test_insufficient_budget_skipped_exit_zero(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    config = _config(tmp_path, max_spend_per_month=10)
    store = WinnowStore(logs / "winnow.sqlite")
    store.record_spend(9.0, "2026-11", None)

    code, reason = scheduled_job(config, logs_dir=logs)
    assert code == 0
    assert "insufficient monthly budget" in reason
    notes = (logs / "notifications.jsonl").read_text(encoding="utf-8")
    assert "insufficient monthly budget" in notes


def test_winnow_halt_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    logs = tmp_path / "logs"
    config = _config(tmp_path)
    monkeypatch.setenv("WINNOW_HALT", "1")
    code, reason = scheduled_job(config, logs_dir=logs)
    assert code == 0
    assert "WINNOW_HALT" in reason
    assert "WINNOW_HALT" in (logs / "notifications.jsonl").read_text(encoding="utf-8")


def test_scheduler_zero_transport_sends(tmp_path: Path) -> None:
    @dataclass
    class SpyTransport:
        calls: int = field(default=0, init=False)

        def send(self, channel, recipient, body, *, candidate_id):
            self.calls += 1
            return "spy"

    logs = tmp_path / "logs"
    config = _config(tmp_path)
    fixture = ManyFixture(rows=[_row(i) for i in range(5)])

    spy = SpyTransport()

    def _reg(_raw: dict) -> None:
        clear()
        register(fixture)

    with patch("winnow.scheduler.register_sources_from_config", _reg):
        with patch("winnow.run.register_sources_from_config", _reg):
            with patch(
                "winnow.outreach.engine.NoopTransport",
                lambda: spy,
            ):
                code, reason = scheduled_job(config, logs_dir=logs)

    assert code == 0
    assert "manual batch staged" in reason or "dry-run complete" in reason
    assert spy.calls == 0
    batches = list(logs.glob("batch_*.json"))
    assert batches, "expected batch file when in bounds"
    data = json.loads(batches[0].read_text(encoding="utf-8"))
    assert data["message_count"] >= 1