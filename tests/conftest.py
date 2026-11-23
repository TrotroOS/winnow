from __future__ import annotations

from datetime import datetime, timezone

import pytest

from winnow.models import Candidate


@pytest.fixture
def make_candidate():
    def _make_candidate(
        *,
        id: str = "cand-1",
        name: str = "Ada Lovelace",
        org: str = "Example Org",
        role: str = "Engineer",
        signals: dict[str, str] | None = None,
        contacts: dict[str, str] | None = None,
        source: str = "fixture",
        collected_at: datetime | None = None,
    ) -> Candidate:
        return Candidate(
            id=id,
            name=name,
            org=org,
            role=role,
            signals=signals or {},
            contacts=contacts or {},
            source=source,
            collected_at=collected_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    return _make_candidate