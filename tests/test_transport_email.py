from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from winnow.criteria.builder import build_criteria, parse_situation
from winnow.models import Candidate, Criteria
from winnow.outreach.batch_send import SendBatchConfig, load_batch_file, send_batch
from winnow.outreach.personalize import MatchedSignalError
from winnow.outreach.sender import OutreachSender
from winnow.outreach.suppression import SuppressionStore
from winnow.outreach.templates import build_message
from winnow.outreach.throttle import Throttle
from winnow.outreach.tracker import OutreachTracker
from winnow.outreach.transport_email import (
    OPT_OUT_LINE,
    EmailDeliveryError,
    EmailTransport,
    email_provider_from_env,
)


@dataclass
class FakeESP:
    sends: list[dict[str, object]] = field(default_factory=list)
    fail_for: set[str] = field(default_factory=set)
    next_id: int = 1

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        headers: dict[str, str],
    ) -> str:
        if to in self.fail_for:
            raise EmailDeliveryError("bounce")
        msg_id = f"msg-{self.next_id}"
        self.next_id += 1
        self.sends.append({"to": to, "subject": subject, "body": body, "headers": dict(headers)})
        return msg_id


@pytest.fixture
def community_batch(tmp_path: Path) -> Path:
    situation = parse_situation(
        {
            "stage": "seed",
            "product": "Winnow",
            "goal": "grow community",
            "constraint": "time",
            "segment": "devtools",
            "channels": ("email",),
            "situation_type": "community",
        }
    )
    criteria, _, name = build_criteria(situation)
    body = build_message(
        name,
        Candidate(
            id="c-1",
            name="Casey",
            org="Dev Club",
            role="Member",
            signals={"community_member": "yes", "activity_days": "2"},
            contacts={"email": "c1@example.com"},
            source="fixture",
            collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        criteria,
    )
    payload = {
        "batch_id": "batch-test",
        "situation_type": name,
        "message_count": 1,
        "messages": [
            {
                "candidate_id": "c-1",
                "channel": "email",
                "recipient": "c1@example.com",
                "body": body,
                "situation_type": name,
                "template_version": "2026.11",
            }
        ],
    }
    path = tmp_path / "batch_test.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_confirm_missing_zero_sends(community_batch: Path) -> None:
    esp = FakeESP()
    transport = EmailTransport(esp, "from@test", "https://x/unsub")
    summary = send_batch(
        community_batch,
        confirm=False,
        config=SendBatchConfig(),
        transport=transport,
    )
    assert summary.sent == 0
    assert esp.sends == []


def test_suppression_blocks_repeat_send(community_batch: Path) -> None:
    esp = FakeESP()
    transport = EmailTransport(esp, "from@test", "https://x/unsub")
    config = SendBatchConfig(daily_cap=10, per_run_send_cap=10, throttle_day=date(2026, 1, 1))
    suppression = SuppressionStore()
    suppression.mark_contacted("c-1")
    batch = load_batch_file(community_batch)
    sender = OutreachSender(
        transport=transport,
        suppression=suppression,
        throttle=Throttle(caps={"email": 10}, day=date(2026, 1, 1)),
        tracker=OutreachTracker(),
        per_run_send_cap=10,
    )
    summary = sender.deliver_batch(batch)
    assert summary.sent == 0
    assert summary.suppressed == 1
    assert esp.sends == []


def test_daily_cap_enforced(community_batch: Path, tmp_path: Path) -> None:
    situation = parse_situation(
        {
            "situation_type": "community",
            "stage": "seed",
            "product": "W",
            "goal": "g",
            "constraint": "c",
            "segment": "devtools",
            "channels": ("email",),
        }
    )
    criteria, _, name = build_criteria(situation)
    messages = []
    for i in range(3):
        cand = Candidate(
            id=f"c-{i}",
            name="N",
            org="O",
            role="Member",
            signals={"community_member": "yes", "activity_days": "1"},
            contacts={"email": f"u{i}@example.com"},
            source="f",
            collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        messages.append(
            {
                "candidate_id": cand.id,
                "channel": "email",
                "recipient": cand.contacts["email"],
                "body": build_message(name, cand, criteria),
                "situation_type": name,
                "template_version": "2026.11",
            }
        )
    path = tmp_path / "batch_many.json"
    path.write_text(
        json.dumps({"batch_id": "b", "messages": messages}),
        encoding="utf-8",
    )
    esp = FakeESP()
    transport = EmailTransport(esp, "from@test", "https://x/unsub")
    summary = send_batch(
        path,
        confirm=True,
        config=SendBatchConfig(daily_cap=2, per_run_send_cap=10, throttle_day=date(2026, 1, 1)),
        transport=transport,
    )
    assert summary.sent == 2
    assert summary.skipped == 1
    assert len(esp.sends) == 2


def test_every_message_has_opt_out_line(community_batch: Path) -> None:
    esp = FakeESP()
    transport = EmailTransport(esp, "from@test", "https://x/unsub")
    send_batch(
        community_batch,
        confirm=True,
        config=SendBatchConfig(throttle_day=date(2026, 1, 1)),
        transport=transport,
    )
    assert len(esp.sends) == 1
    body = str(esp.sends[0]["body"])
    assert OPT_OUT_LINE.strip() in body
    headers = esp.sends[0]["headers"]
    assert isinstance(headers, dict)
    assert "List-Unsubscribe" in headers


def test_no_matched_signal_raises_never_sends() -> None:
    candidate = Candidate(
        id="opaque",
        name="X",
        org="O",
        role="R",
        signals={},
        contacts={"email": "x@example.com"},
        source="f",
        collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    criteria = [Criteria(name="opaque", predicate=lambda _: True, cost=0)]
    esp = FakeESP()
    with pytest.raises(MatchedSignalError):
        build_message("community", candidate, criteria)
    assert esp.sends == []


def test_tracker_records_provider_id_and_bounce(community_batch: Path, tmp_path: Path) -> None:
    esp = FakeESP()
    esp_ok = FakeESP()
    transport_ok = EmailTransport(esp_ok, "from@test", "https://x/unsub")

    batch = load_batch_file(community_batch)
    tracker = OutreachTracker()
    sender = OutreachSender(
        transport=transport_ok,
        suppression=SuppressionStore(),
        throttle=Throttle(caps={"email": 5}, day=date(2026, 1, 1)),
        tracker=tracker,
    )
    sender.deliver_batch(batch)
    assert any(
        r.provider_message_id == "msg-1" and r.status == "sent" for r in tracker.records
    )

    esp_fail = FakeESP(fail_for={"c1@example.com"})
    transport_fail = EmailTransport(esp_fail, "from@test", "https://x/unsub")
    tracker2 = OutreachTracker()
    sender2 = OutreachSender(
        transport=transport_fail,
        suppression=SuppressionStore(),
        throttle=Throttle(caps={"email": 5}, day=date(2026, 1, 1)),
        tracker=tracker2,
    )
    sender2.deliver_batch(batch)
    assert any(r.status == "bounced" for r in tracker2.records)


def test_email_provider_from_env_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WINNOW_EMAIL_PROVIDER", raising=False)
    with pytest.raises(Exception, match="WINNOW_EMAIL_PROVIDER"):
        email_provider_from_env()