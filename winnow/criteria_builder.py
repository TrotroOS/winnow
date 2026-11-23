"""Build criteria predicates for a situation (stub)."""

from __future__ import annotations

from winnow.models import Candidate, Criterion


def build_criteria(situation_type: str) -> list[Criterion]:
    """Return default criteria for a situation. Stub uses a single org-present rule."""
    _ = situation_type

    def has_org(candidate: Candidate) -> bool:
        return bool(candidate.org.strip())

    return [Criterion(name="has_org", predicate=has_org)]