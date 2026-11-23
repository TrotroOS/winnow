from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from winnow.filter import apply_filter, reachable
from winnow.models import Candidate, Criteria
from winnow.orchestrator import RunConfig, run
from winnow.outreach.batch_send import SendBatch, SendBatchConfig, send_batch
from winnow.outreach.engine import run_outreach
from winnow.outreach.guards import audit_blocks_auto_send, resolve_manual_approve
from winnow.outreach.sender import OutboundMessage, OutreachSender
from winnow.outreach.suppression import SuppressionStore
from winnow.outreach.throttle import Throttle
from winnow.outreach.tracker import OutreachTracker


def _community_candidate(cid: str) -> Candidate:
    return Candidate(
        id=cid,
        name="Casey",
        org="Dev Club",
        role="Member",
        signals={"community_member": "yes", "activity_days": "2"},
        contacts={"email": f"{cid}@example.com"},
        source="fixture",
        collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _append_audit(path: Path, outreach: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"outreach": outreach}) + "\n")


@dataclass
class SpyTransport:
    calls: list[str] = field(default_factory=list)

    def send(self, channel, recipient, body, *, candidate_id) -> str:
        if not reachable(Candidate(
            id=candidate_id,
            name="",
            org="",
            role="",
            signals={"community_member": "yes", "activity_days": "1"},
            contacts={"email": recipient},
            source="x",
            collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )):
            raise AssertionError("non-reachable candidate reached send path")
        self.calls.append(candidate_id)
        return f"msg-{candidate_id}"


def test_kill_switch_blocks_auto_send(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WINNOW_HALT", "1")
    transport = SpyTransport()
    criteria = [
        Criteria(
            name="community_member",
            predicate=lambda c: c.signals.get("community_member") == "yes",
            cost=0,
        )
    ]
    possible = [_community_candidate("ok-1")]
    summary = run_outreach(
        possible,
        situation_type="community",
        criteria=criteria,
        batch_size=10,
        manual_approve=False,
        transport=transport,
        throttle_caps={"email": 100, "linkedin": 0, "dm": 0},
        per_run_send_cap=25,
    )
    assert transport.calls == []
    assert summary.sent == 0
    assert summary.skipped == 1


def test_kill_switch_blocks_confirmed_batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WINNOW_HALT", "1")
    batch_path = tmp_path / "batch.json"
    batch_path.write_text(
        json.dumps(
            {
                "batch_id": "b1",
                "messages": [
                    {
                        "candidate_id": "c1",
                        "channel": "email",
                        "recipient": "a@b.co",
                        "body": "Hi",
                        "situation_type": "community",
                        "template_version": "2026.11",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    summary = send_batch(
        batch_path,
        confirm=True,
        config=SendBatchConfig(daily_cap=25, per_run_send_cap=25),
    )
    assert summary.sent == 0
    assert summary.skipped == 1


def test_bounce_guard_refuses_auto_send(tmp_path: Path) -> None:
    audit = tmp_path / "runs.jsonl"
    _append_audit(audit, {"sent": 10, "replied": 0, "bounced": 0})
    blocked, _ = audit_blocks_auto_send(audit)
    assert blocked
    manual, warning = resolve_manual_approve("auto_send", audit_log_path=audit)
    assert manual is True
    assert warning is not None
    assert "auto_send refused" in warning


def test_auto_send_caps_match_manual_engine() -> None:
    transport = SpyTransport()
    rows = [_community_candidate(f"c{i}") for i in range(5)]
    criteria = [
        Criteria(
            name="community_member",
            predicate=lambda c: c.signals.get("community_member") == "yes",
            cost=0,
        )
    ]
    manual_summary = run_outreach(
        rows,
        situation_type="community",
        criteria=criteria,
        batch_size=10,
        manual_approve=True,
        transport=transport,
        throttle_caps={"email": 2, "linkedin": 0, "dm": 0},
        per_run_send_cap=2,
    )
    assert manual_summary.sent == 0
    assert manual_summary.skipped == 5

    transport2 = SpyTransport()
    auto_summary = run_outreach(
        rows,
        situation_type="community",
        criteria=criteria,
        batch_size=10,
        manual_approve=False,
        transport=transport2,
        throttle_caps={"email": 2, "linkedin": 0, "dm": 0},
        per_run_send_cap=2,
    )
    assert auto_summary.sent == 2
    assert auto_summary.skipped == 3
    assert len(transport2.calls) == 2


def test_non_possible_never_reaches_send_in_manual_or_auto() -> None:
    criteria = [
        Criteria(name="always", predicate=lambda _: True, cost=0),
        Criteria(
            name="community_member",
            predicate=lambda c: c.signals.get("community_member") == "yes",
            cost=1,
        ),
    ]
    reachable_row = _community_candidate("good")
    noise = Candidate(
        id="noise",
        name="X",
        org="Y",
        role="Z",
        signals={},
        contacts={"email": "n@example.com"},
        source="fixture",
        collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    possible, dropped = apply_filter([reachable_row, noise], criteria, reachable)
    assert dropped == 1
    assert [c.id for c in possible] == ["good"]

    @dataclass
    class StrictSpy:
        ids_seen: list[str] = field(default_factory=list)

        def send(self, channel, recipient, body, *, candidate_id) -> str:
            allowed = {c.id for c in possible}
            if candidate_id not in allowed:
                raise AssertionError(f"non-POSSIBLE {candidate_id!r} reached send")
            self.ids_seen.append(candidate_id)
            return "ok"

    for manual in (True, False):
        spy = StrictSpy()
        summary = run_outreach(
            possible,
            situation_type="community",
            criteria=criteria,
            batch_size=5,
            manual_approve=manual,
            transport=spy,
            throttle_caps={"email": 100, "linkedin": 0, "dm": 0},
            per_run_send_cap=10,
        )
        if manual:
            assert summary.sent == 0
            assert spy.ids_seen == []
        else:
            assert spy.ids_seen == ["good"]
            assert summary.sent == 1


def test_orchestrator_passes_auto_send_caps(tmp_path: Path) -> None:
    from unittest.mock import patch

    from winnow.models import OutreachSummary

    situation = {
        "situation_type": "community",
        "stage": "seed",
        "product": "Winnow",
        "goal": "community: grow",
        "constraint": "time",
        "segment": "devtools",
        "channels": ("email",),
    }
    from winnow.sources.mock import MockSource
    from winnow.sources.registry import clear, register

    clear()
    register(MockSource())
    cfg = RunConfig(
        manual_approve=False,
        dry_run=True,
        max_sends_per_run=1,
        daily_cap=100,
        audit_log_path=tmp_path / "runs.jsonl",
        spend_log_path=tmp_path / "spend.json",
        search_limit=50,
    )
    with patch("winnow.orchestrator.run_outreach") as mock_ro:
        mock_ro.return_value = OutreachSummary()
        run(situation, cfg)
        _, kwargs = mock_ro.call_args
        assert kwargs["per_run_send_cap"] == 1
        assert kwargs["manual_approve"] is False