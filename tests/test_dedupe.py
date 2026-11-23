from __future__ import annotations

from winnow.dedupe import dedupe_by_id
from winnow.models import Candidate


def test_dedupe_keeps_first_id(sample_candidates: list[Candidate]) -> None:
    deduped = dedupe_by_id(sample_candidates)
    assert len(deduped) == 3
    ada = next(c for c in deduped if c.id == "c1")
    assert ada.source == "fixture"