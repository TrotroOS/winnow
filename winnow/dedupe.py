"""Deduplicate candidates by id (pure)."""

from __future__ import annotations

from winnow.models import Candidate


def dedupe_by_id(candidates: list[Candidate]) -> list[Candidate]:
    """Keep first occurrence per candidate id."""
    seen: set[str] = set()
    out: list[Candidate] = []
    for c in candidates:
        if c.id in seen:
            continue
        seen.add(c.id)
        out.append(c)
    return out