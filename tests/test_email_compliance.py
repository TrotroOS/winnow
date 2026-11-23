from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from winnow.models import Candidate
from winnow.outreach.batch_send import SendBatchConfig, load_batch_file, send_batch
from winnow.outreach.domain_throttle import RecipientDomainThrottle
from winnow.outreach.opt_out import apply_opt_out, reply_indicates_opt_out
from winnow.outreach.sender import OutreachSender
from winnow.outreach.suppression import SuppressionStore
from winnow.outreach.throttle import Throttle
from winnow.outreach.tracker import OutreachTracker
from winnow.outreach.transport_email import (
    EmailHardBounceError,
    EmailSoftBounceError,
    EmailTransport,
)
from winnow.store import WinnowStore


@dataclass
class BounceESP:
    soft_for: set[str] = field(default_factory=set)
    hard_for: set[str] = field(default_factory=set)
    sends: list[dict[str, object]] = field(default_factory=list)
    next_id: int = 1
    soft_attempts: dict[str, int] = field(default_factory=dict)

    def send_email(
        self,
        to: str,
        subject: str,
        body_plain: str,
        *,
        body_html: str | None = None,
        headers: dict[str, str],
    ) -> str:
        if to in self.hard_for:
            raise EmailHardBounceError("hard bounce")
        if to in self.soft_for:
            count = self.soft_attempts.get(to, 0) + 1
            self.soft_attempts[to] = count
            raise EmailSoftBounceError("soft bounce")
        msg_id = f"msg-{self.next_id}"
        self.next_id += 1
        self.sends.append({"to": to, "body": body_plain})
        return msg_id


def _batch_json(tmp_path: Path, recipient: str, *, cid: str = "c-1") -> Path:
    payload = {
        "batch_id": "b",
        "messages": [
            {
                "candidate_id": cid,
                "channel": "email",
                "recipient": recipient,
                "body": "Hello",
                "situation_type": "community",
                "template_version": "2026.11",
            }
        ],
    }
    path = tmp_path / "batch.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_hard_bounce_suppresses_in_store(tmp_path: Path) -> None:
    db = tmp_path / "winnow.sqlite"
    store = WinnowStore(db)
    store.save_candidate(
        Candidate(
            id="c-1",
            name="A",
            org="O",
            role="",
            signals={},
            contacts={"email": "bad@example.com"},
            source="f",
            collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        "possible",
    )
    esp = BounceESP(hard_for={"bad@example.com"})
    transport = EmailTransport(esp, "from@test", "https://x/u?c={candidate_id}")
    suppression = SuppressionStore(store=store)
    batch = load_batch_file(_batch_json(tmp_path, "bad@example.com"))
    sender = OutreachSender(
        transport=transport,
        suppression=suppression,
        throttle=Throttle(caps={"email": 5}, day=date(2026, 1, 1)),
        tracker=OutreachTracker(),
        store=store,
    )
    summary = sender.deliver_batch(batch)
    assert summary.sent == 0
    assert summary.bounced == 1
    assert "c-1" in store.suppression_ids()
    assert store.get_candidate_row("c-1")["status"] == "bounced"


def test_soft_bounce_suppress_after_three_attempts(tmp_path: Path) -> None:
    db = tmp_path / "winnow.sqlite"
    store = WinnowStore(db)
    store.save_candidate(
        Candidate(
            id="c-1",
            name="A",
            org="O",
            role="",
            signals={},
            contacts={"email": "soft@example.com"},
            source="f",
            collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        "possible",
    )
    esp = BounceESP(soft_for={"soft@example.com"})
    transport = EmailTransport(esp, "from@test", "https://x/u?c={candidate_id}")
    suppression = SuppressionStore(store=store)
    batch_path = _batch_json(tmp_path, "soft@example.com")
    sender = OutreachSender(
        transport=transport,
        suppression=suppression,
        throttle=Throttle(caps={"email": 5}, day=date(2026, 1, 1)),
        tracker=OutreachTracker(),
        store=store,
    )
    for _ in range(3):
        sender.deliver_batch(load_batch_file(batch_path))
    assert store.get_candidate_row("c-1")["bounce_attempts"] >= 3
    assert "c-1" in store.suppression_ids()


def test_opt_out_reply_and_link_status(tmp_path: Path) -> None:
    store = WinnowStore(tmp_path / "winnow.sqlite")
    store.save_candidate(
        Candidate(
            id="c-9",
            name="A",
            org="O",
            role="",
            signals={},
            contacts={"email": "a@example.com"},
            source="f",
            collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        "contacted",
    )
    assert reply_indicates_opt_out("UNSUBSCRIBE")
    assert reply_indicates_opt_out("  please opt out  ")
    suppression = SuppressionStore(store=store)
    apply_opt_out(
        "c-9",
        template_version="2026.11",
        store=store,
        suppression=suppression,
        tracker=OutreachTracker(),
    )
    assert store.get_candidate_row("c-9")["status"] == "opted_out"
    assert "c-9" in store.suppression_ids()
    assert store.get_candidate_row("c-9")["suppression_hash"]


def test_per_domain_hourly_limit(tmp_path: Path) -> None:
    esp = BounceESP()
    transport = EmailTransport(esp, "from@test", "https://x/u?c={candidate_id}")
    messages = []
    for i in range(3):
        messages.append(
            {
                "candidate_id": f"c-{i}",
                "channel": "email",
                "recipient": f"user{i}@samecorp.com",
                "body": "Hi",
                "situation_type": "community",
                "template_version": "2026.11",
            }
        )
    path = tmp_path / "many.json"
    path.write_text(json.dumps({"batch_id": "b", "messages": messages}), encoding="utf-8")
    summary = send_batch(
        path,
        confirm=True,
        config=SendBatchConfig(
            daily_cap=10,
            max_per_hour_per_recipient_domain=2,
            throttle_day=date(2026, 1, 1),
        ),
        transport=transport,
    )
    assert summary.sent == 2
    assert summary.skipped == 1


def test_recipient_domain_throttle_unit() -> None:
    throttle = RecipientDomainThrottle(max_per_hour=2)
    when = datetime(2026, 6, 1, 12, 30, tzinfo=timezone.utc)
    assert throttle.allow("a@Foo.com", now=when)
    throttle.record("a@foo.com", now=when)
    throttle.record("b@foo.com", now=when)
    assert not throttle.allow("c@foo.com", now=when)


def test_retention_anonymize(tmp_path: Path) -> None:
    store = WinnowStore(tmp_path / "winnow.sqlite")
    store.save_candidate(
        Candidate(
            id="old-1",
            name="Stale",
            org="Org",
            role="",
            signals={},
            contacts={"email": "old@example.com"},
            source="f",
            collected_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        ),
        "possible",
    )
    conn = store._conn
    stale = (datetime(2026, 1, 1, tzinfo=timezone.utc) - timedelta(days=400)).isoformat()
    conn.execute("UPDATE candidates SET last_seen = ?", (stale,))
    conn.commit()
    count = store.anonymize_stale_candidates(
        365, now=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    assert count == 1
    row = store.get_candidate_row("old-1")
    assert row["name"] == "[anonymized]"
    assert json.loads(row["contacts_json"]) == {}
    assert row["suppression_hash"]


def test_gdpr_erase_keeps_hash(tmp_path: Path) -> None:
    from winnow.privacy import erase_candidate, export_candidate

    store = WinnowStore(tmp_path / "winnow.sqlite")
    store.save_candidate(
        Candidate(
            id="gdpr-1",
            name="Pat",
            org="Org",
            role="",
            signals={},
            contacts={"email": "pat@example.com"},
            source="f",
            collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        "contacted",
    )
    exported = export_candidate(store, "gdpr-1")
    assert exported["contacts"]["email"] == "pat@example.com"
    erase_candidate(store, "gdpr-1")
    row = store.get_candidate_row("gdpr-1")
    assert row["name"] == "[erased]"
    assert json.loads(row["contacts_json"]) == {}
    assert row["suppression_hash"]
    with pytest.raises(KeyError):
        export_candidate(store, "missing")