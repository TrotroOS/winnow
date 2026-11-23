from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import pytest

from winnow.criteria.builder import build_criteria, parse_situation
from winnow.filter import apply_filter
from winnow.models import Candidate, Criteria
from winnow.outreach.batcher import group_by_channel, primary_channel
from winnow.outreach.personalize import MatchedSignalError, matched_signal
from winnow.outreach.sender import OutreachSender
from winnow.outreach.suppression import SuppressionStore
from winnow.outreach.templates import build_message
from winnow.outreach.throttle import Throttle
from winnow.outreach.tracker import OutreachTracker


@dataclass
class SpyTransport:
    calls: list[tuple[str, str, str, str]] = field(default_factory=list)

    def send(
        self,
        channel: str,
        recipient: str,
        body: str,
        *,
        candidate_id: str,
    ) -> str:
        self.calls.append((candidate_id, channel, recipient, body))
        return f"spy-{candidate_id}"


def _community_situation_data() -> dict:
    return {
        "stage": "seed",
        "product": "Winnow",
        "goal": "grow community",
        "constraint": "time",
        "segment": "devtools",
        "channels": ("email",),
        "situation_type": "community",
    }


def _community_candidate(*, id: str, **overrides: object) -> Candidate:
    base = dict(
        id=id,
        name="Casey",
        org="Dev Club",
        role="Member",
        signals={"community_member": "yes", "activity_days": "2"},
        contacts={"email": f"{id}@example.com"},
        source="fixture",
    )
    base.setdefault("collected_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    base.update(overrides)
    return Candidate(**base)  # type: ignore[arg-type]


def _sender(
    transport: SpyTransport,
    *,
    caps: dict[str, int] | None = None,
    suppression: SuppressionStore | None = None,
) -> OutreachSender:
    return OutreachSender(
        transport=transport,
        suppression=suppression or SuppressionStore(),
        throttle=Throttle(caps=caps, day=date(2026, 1, 1)),
        tracker=OutreachTracker(),
    )


def test_suppression_blocks_duplicate_send() -> None:
    transport = SpyTransport()
    suppression = SuppressionStore()
    sender = _sender(transport, suppression=suppression)
    situation = parse_situation(_community_situation_data())
    criteria, _, name = build_criteria(situation)
    candidate = _community_candidate(id="c-1")

    batch = sender.build_batch(
        situation_type=name,
        possible=[candidate],
        criteria=criteria,
        manual_approve=False,
    )
    assert transport.calls
    assert len(transport.calls) == 1

    transport.calls.clear()
    batch2 = sender.build_batch(
        situation_type=name,
        possible=[candidate],
        criteria=criteria,
        manual_approve=False,
    )
    assert transport.calls == []
    assert batch2.messages == []


def test_throttle_caps_enforced_at_send() -> None:
    transport = SpyTransport()
    sender = _sender(transport, caps={"email": 1})
    situation = parse_situation(_community_situation_data())
    criteria, _, name = build_criteria(situation)
    rows = [
        _community_candidate(id="a"),
        _community_candidate(id="b"),
    ]
    batch = sender.build_batch(
        situation_type=name,
        possible=rows,
        criteria=criteria,
        manual_approve=True,
    )
    summary = sender.confirm_send(batch.batch_id)
    assert len(transport.calls) == 1
    assert summary.sent == 1
    assert summary.skipped == 1


def test_manual_approve_sends_nothing_without_confirm() -> None:
    transport = SpyTransport()
    sender = _sender(transport)
    situation = parse_situation(_community_situation_data())
    criteria, _, name = build_criteria(situation)
    candidate = _community_candidate(id="manual-1")

    batch = sender.build_batch(
        situation_type=name,
        possible=[candidate],
        criteria=criteria,
        manual_approve=True,
    )
    assert batch.messages
    assert transport.calls == []

    summary = sender.confirm_send(batch.batch_id)
    assert summary.sent == 1
    assert len(transport.calls) == 1


def test_no_matched_signal_raises_not_send() -> None:
    candidate = _community_candidate(
        id="opaque",
        signals={},
        contacts={"email": "x@example.com"},
    )
    criteria = [
        Criteria(name="opaque_gate", predicate=lambda _: True, cost=0),
    ]
    with pytest.raises(MatchedSignalError):
        matched_signal(candidate, criteria)
    with pytest.raises(MatchedSignalError):
        build_message("community", candidate, criteria)


def test_primary_channel_precedence() -> None:
    candidate = Candidate(
        id="ch",
        name="N",
        org="O",
        role="R",
        signals={},
        contacts={
            "dm": "@h",
            "linkedin": "https://li/in/x",
            "email": "a@b.co",
        },
        source="s",
        collected_at=_community_candidate(id="x").collected_at,
    )
    assert primary_channel(candidate) == "email"
    grouped = group_by_channel([candidate])
    assert list(grouped) == ["email"]


def test_filter_integration_only_possible_ids_sent() -> None:
    transport = SpyTransport()
    sender = _sender(transport)
    situation = parse_situation(_community_situation_data())
    criteria, reachability, name = build_criteria(situation)

    good = _community_candidate(id="good-1")
    noise = Candidate(
        id="noise-1",
        name="Noise",
        org="Bad",
        role="Intern",
        signals={},
        contacts={"email": "noise@example.com"},
        source="mock",
        collected_at=good.collected_at,
    )
    pool = [good, noise]
    possible, dropped = apply_filter(pool, criteria, reachability)
    assert dropped == 1
    possible_ids = {c.id for c in possible}

    batch = sender.build_batch(
        situation_type=name,
        possible=possible,
        criteria=criteria,
        manual_approve=False,
    )
    sent_ids = {call[0] for call in transport.calls}
    assert sent_ids <= possible_ids
    assert "noise-1" not in sent_ids
    assert sent_ids == {"good-1"}
    assert {m.candidate_id for m in batch.messages} == sent_ids