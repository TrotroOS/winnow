from __future__ import annotations

from datetime import datetime, timezone

from winnow.models import Candidate
from winnow.reachability import default_reachable


def _candidate(contacts: dict[str, str]) -> Candidate:
    return Candidate(
        id="x",
        name="Test",
        org="Org",
        role="Role",
        signals={},
        contacts=contacts,
        source="test",
        collected_at=datetime.now(timezone.utc),
    )


def test_reachable_with_email() -> None:
    assert default_reachable(_candidate({"email": "a@b.com"}))


def test_not_reachable_empty_contacts() -> None:
    assert not default_reachable(_candidate({}))


def test_not_reachable_blank_email() -> None:
    assert not default_reachable(_candidate({"email": "   "}))