from __future__ import annotations

from datetime import datetime, timezone

from winnow.models import Candidate
from winnow.normalize import _EPOCH_UTC, dedupe, normalize


def test_normalize_maps_all_fields() -> None:
    collected = datetime(2026, 3, 1, 15, 30, tzinfo=timezone.utc)
    raw = {
        "id": "src-9",
        "name": "Alex Kim",
        "org": "Winnow Labs",
        "role": "CEO",
        "signals": {"segment": "b2b", "stage": "seed"},
        "contacts": {"email": "alex@winnow.test"},
        "collected_at": collected,
    }
    candidate = normalize(raw, source="mock")
    assert candidate == Candidate(
        id="src-9",
        name="Alex Kim",
        org="Winnow Labs",
        role="CEO",
        signals={"segment": "b2b", "stage": "seed"},
        contacts={"email": "alex@winnow.test"},
        source="mock",
        collected_at=collected,
    )


def test_normalize_missing_fields_are_empty_not_inferred() -> None:
    raw = {
        "role": "Engineer",
        "signals": "not-a-dict",
        "name": "Only Name",
        # org deliberately omitted — must stay empty, not copied from name/role
    }
    candidate = normalize(raw, source="api_x")
    assert candidate.id == ""
    assert candidate.name == "Only Name"
    assert candidate.org == ""
    assert candidate.role == "Engineer"
    assert candidate.signals == {}
    assert candidate.contacts == {}
    assert candidate.source == "api_x"
    assert candidate.collected_at == _EPOCH_UTC


def test_normalize_parses_iso_collected_at_string() -> None:
    raw = {"collected_at": "2026-06-10T09:00:00+00:00", "name": "N"}
    candidate = normalize(raw, source="s")
    assert candidate.collected_at == datetime(2026, 6, 10, 9, tzinfo=timezone.utc)


def test_dedupe_keeps_newest_collected_at() -> None:
    older = Candidate(
        id="",
        name="Sam Lee",
        org="Acme",
        role="CTO",
        signals={},
        contacts={},
        source="mock",
        collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    newer = Candidate(
        id="",
        name="sam lee",
        org=" ACME ",
        role="Founder",
        signals={"tier": "yes"},
        contacts={"email": "sam@acme.test"},
        source="mock",
        collected_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    survivors, dropped = dedupe([older, newer])
    assert dropped == 1
    assert survivors == [newer]
    assert survivors[0].role == "Founder"


def test_dedupe_preserves_stable_first_occurrence_order() -> None:
    a_old = Candidate(
        id="a-1",
        name="A",
        org="Org1",
        role="r1",
        signals={},
        contacts={},
        source="s",
        collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    b = Candidate(
        id="b-1",
        name="B",
        org="Org2",
        role="r2",
        signals={},
        contacts={},
        source="s",
        collected_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    a_new = Candidate(
        id="a-1",
        name="A",
        org="Org1",
        role="r1-new",
        signals={},
        contacts={},
        source="s",
        collected_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    survivors, dropped = dedupe([a_old, b, a_new])
    assert dropped == 1
    assert [c.id for c in survivors] == ["a-1", "b-1"]
    assert survivors[0].role == "r1-new"
    assert survivors[1] is b


def test_dedupe_drop_count_matches_inputs() -> None:
    shared = dict(
        name="Pat",
        org="Co",
        role="",
        signals={},
        contacts={},
        source="mock",
        collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    rows = [
        Candidate(id="", **shared),
        Candidate(id="", **shared),
        Candidate(id="", **shared),
        Candidate(
            id="unique",
            name="Other",
            org="Else",
            role="",
            signals={},
            contacts={},
            source="mock",
            collected_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
    ]
    survivors, dropped = dedupe(rows)
    assert dropped == 2
    assert len(survivors) == 2