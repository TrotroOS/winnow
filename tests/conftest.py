from __future__ import annotations

from datetime import datetime, timezone

import pytest

from winnow.models import Candidate


@pytest.fixture
def sample_candidates() -> list[Candidate]:
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        Candidate(
            id="c1",
            name="Ada Lovelace",
            org="Analytical Engines",
            role="CTO",
            signals={"stage": "seed"},
            contacts={"email": "ada@example.com"},
            source="fixture",
            collected_at=now,
        ),
        Candidate(
            id="c2",
            name="Bob Null",
            org="",
            role="Founder",
            signals={},
            contacts={"email": "bob@example.com"},
            source="fixture",
            collected_at=now,
        ),
        Candidate(
            id="c3",
            name="Carol Offline",
            org="Quiet Co",
            role="CEO",
            signals={},
            contacts={},
            source="fixture",
            collected_at=now,
        ),
        Candidate(
            id="c1",
            name="Ada Lovelace",
            org="Analytical Engines",
            role="CTO",
            signals={"stage": "seed"},
            contacts={"email": "ada@example.com"},
            source="fixture_dup",
            collected_at=now,
        ),
    ]