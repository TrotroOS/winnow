from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from winnow.criteria.builder import build_criteria, parse_situation
from winnow.filter import apply_filter, reachable
from winnow.models import Candidate, Criteria
from winnow.outreach.batch_send import SendBatchConfig, send_batch
from winnow.outreach.batcher import channel_priority_from_config, primary_channel
from winnow.outreach.guards import resolve_manual_approve
from winnow.outreach.engine import run_outreach
from winnow.outreach.sender import OutreachSender
from winnow.outreach.suppression import SuppressionStore
from winnow.outreach.templates import build_message
from winnow.outreach.throttle import Throttle
from winnow.outreach.tracker import OutreachTracker
from winnow.outreach.transport_linkedin import (
    SECOND_CHANNEL,
    LinkedInTransport,
    linkedin_candidate_eligible,
)
from winnow.outreach.routing_transport import ChannelRouterTransport
from winnow.outreach.transport_email import EmailTransport


@dataclass
class FakeLinkedIn:
    sends: list[dict[str, object]] = field(default_factory=list)
    next_id: int = 1

    def send_message(self, profile_url: str, body: str, *, candidate_id: str) -> str:
        msg_id = f"li-{self.next_id}"
        self.next_id += 1
        self.sends.append(
            {"profile": profile_url, "body": body, "candidate_id": candidate_id}
        )
        return msg_id


@dataclass
class FakeESP:
    sends: list[dict[str, object]] = field(default_factory=list)
    next_id: int = 1

    def send_email(self, to, subject, body, *, headers):
        msg_id = f"em-{self.next_id}"
        self.next_id += 1
        self.sends.append({"to": to})
        return msg_id


def _community_criteria() -> list[Criteria]:
    situation = parse_situation(
        {
            "stage": "seed",
            "product": "Winnow",
            "goal": "grow community",
            "constraint": "time",
            "segment": "devtools",
            "channels": ("email", "linkedin"),
            "situation_type": "community",
        }
    )
    criteria, _, _ = build_criteria(situation)
    return criteria


def _candidate(
    cid: str,
    *,
    activity_days: str = "2",
    contacts: dict[str, str] | None = None,
    signals: dict[str, str] | None = None,
) -> Candidate:
    base_signals = {"community_member": "yes", "activity_days": activity_days}
    if signals:
        base_signals.update(signals)
    contact = contacts or {
        "email": f"{cid}@example.com",
        "linkedin": f"https://linkedin.com/in/{cid}",
    }
    return Candidate(
        id=cid,
        name=f"User {cid}",
        org="Dev Club",
        role="Member",
        signals=base_signals,
        contacts=contact,
        source="fixture",
        collected_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )


def test_auto_send_refused_for_linkedin_channel() -> None:
    manual, warning = resolve_manual_approve(
        "auto_send",
        audit_log_path=Path("nope.jsonl"),
        outreach_channels=("email", "linkedin"),
    )
    assert manual is True
    assert warning is not None
    assert "LinkedIn" in warning
    assert "manual" in warning.lower()


def test_channel_priority_default_email_before_linkedin() -> None:
    order = channel_priority_from_config({"second_channel": SECOND_CHANNEL})
    assert order == ("email", "linkedin", "dm")
    c = _candidate("prio")
    assert primary_channel(c, priority=order) == "email"


def test_channel_priority_respects_config_list() -> None:
    order = channel_priority_from_config(
        {"channel_priority": ["linkedin", "email", "dm"]}
    )
    c = _candidate("prio2")
    assert primary_channel(c, priority=order) == "linkedin"


def test_stale_or_missing_matched_signal_skipped_for_linkedin() -> None:
    criteria = _community_criteria()
    stale = _candidate("stale", activity_days="40")
    sender = OutreachSender(
        transport=LinkedInTransport(FakeLinkedIn()),
        suppression=SuppressionStore(),
        throttle=Throttle(),
        tracker=OutreachTracker(),
    )
    batch = sender.build_batch(
        situation_type="community",
        possible=[stale],
        criteria=criteria,
        channel_priority=("linkedin", "email"),
        linkedin_max_signal_age_days=7,
    )
    assert batch.messages == []

    no_signal = Candidate(
        id="nosig",
        name="N",
        org="O",
        role="R",
        signals={},
        contacts={"linkedin": "https://linkedin.com/in/nosig"},
        source="fixture",
        collected_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    assert not linkedin_candidate_eligible(
        no_signal, criteria, max_age_days=30
    )


def test_daily_cap_twenty_enforced_for_linkedin(tmp_path: Path) -> None:
    criteria = _community_criteria()
    messages = []
    for i in range(22):
        c = _candidate(f"li-{i}")
        body = build_message("community", c, criteria)
        messages.append(
            {
                "candidate_id": c.id,
                "channel": "linkedin",
                "recipient": c.contacts["linkedin"],
                "body": body,
                "situation_type": "community",
                "template_version": "2026.11",
            }
        )
    batch_path = tmp_path / "batch_li.json"
    batch_path.write_text(
        json.dumps({"batch_id": "b", "message_count": 22, "messages": messages}),
        encoding="utf-8",
    )
    li = FakeLinkedIn()
    em = FakeESP()
    transport = ChannelRouterTransport(
        linkedin=LinkedInTransport(li),
        email=EmailTransport(em, "from@test", "https://x/unsub"),
    )
    summary = send_batch(
        batch_path,
        confirm=True,
        config=SendBatchConfig(
            daily_cap=25,
            linkedin_daily_cap=20,
            throttle_day=date(2026, 11, 1),
        ),
        transport=transport,
    )
    assert summary.sent == 20
    assert summary.skipped == 2
    assert len(li.sends) == 20
    assert em.sends == []


def test_spy_no_non_possible_in_linkedin_or_email_transports() -> None:
    @dataclass
    class Spy:
        calls: list[str] = field(default_factory=list)

        def send(self, channel, recipient, body, *, candidate_id) -> str:
            probe = Candidate(
                id=candidate_id,
                name="",
                org="",
                role="",
                signals={"community_member": "yes", "activity_days": "1"},
                contacts={channel: recipient},
                source="x",
                collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
            if not reachable(probe):
                raise AssertionError(f"non-reachable {candidate_id}")
            self.calls.append(candidate_id)
            return "ok"

        def send_message(self, profile_url, body, *, candidate_id: str) -> str:
            return self.send(
                "linkedin", profile_url, body, candidate_id=candidate_id
            )

    situation = parse_situation(
        {
            "stage": "seed",
            "product": "Winnow",
            "goal": "grow community",
            "constraint": "time",
            "segment": "devtools",
            "channels": ("linkedin",),
            "situation_type": "community",
        }
    )
    criteria, reach_fn, _ = build_criteria(situation)
    good = _candidate("good-1")
    noise = Candidate(
        id="noise-1",
        name="Noise",
        org="Bad",
        role="Intern",
        signals={},
        contacts={"linkedin": "https://li/noise"},
        source="fixture",
        collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    possible, _ = apply_filter([good, noise], criteria, reach_fn)
    assert [c.id for c in possible] == ["good-1"]

    spy = Spy()
    transport = ChannelRouterTransport(linkedin=LinkedInTransport(spy))
    summary = run_outreach(
        possible,
        situation_type="community",
        criteria=criteria,
        batch_size=10,
        manual_approve=False,
        transport=transport,
        throttle_caps={"email": 0, "linkedin": 50, "dm": 0},
        channel_priority=("linkedin", "email"),
    )
    assert summary.sent == 1
    assert spy.calls == ["good-1"]


def test_linkedin_message_includes_matched_signal_hook() -> None:
    criteria = _community_criteria()
    c = _candidate("hook")
    body = build_message("community", c, criteria)
    assert "community" in body.lower() or "active" in body.lower()