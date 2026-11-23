"""Build pure bool criteria from a parsed Situation."""

from __future__ import annotations

from winnow.models import Candidate, Criterion, Situation


def _text_fields(candidate: Candidate) -> str:
    parts = [candidate.name, candidate.org, candidate.role]
    for value in candidate.signals.values():
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts).lower()


def build_criteria(situation: Situation) -> list[Criterion]:
    """Return binary predicates for the situation. No scores or weights."""
    criteria: list[Criterion] = []

    def has_org(candidate: Candidate) -> bool:
        return bool(candidate.org.strip())

    criteria.append(Criterion(name="has_org", predicate=has_org))

    if situation.role_hints:

        def role_hint_match(candidate: Candidate) -> bool:
            role = candidate.role.lower()
            return any(hint in role for hint in situation.role_hints)

        criteria.append(Criterion(name="role_hint_match", predicate=role_hint_match))

    if situation.sector_hints:

        def sector_hint_match(candidate: Candidate) -> bool:
            haystack = _text_fields(candidate)
            signal_sector = str(candidate.signals.get("sector", "")).lower()
            return any(
                hint in haystack or hint in signal_sector for hint in situation.sector_hints
            )

        criteria.append(Criterion(name="sector_hint_match", predicate=sector_hint_match))

    if situation.geography:

        def geography_match(candidate: Candidate) -> bool:
            geo = situation.geography or ""
            geo_lower = geo.lower()
            signal_geo = str(candidate.signals.get("geography", "")).lower()
            return geo_lower in _text_fields(candidate) or geo_lower in signal_geo

        criteria.append(Criterion(name="geography_match", predicate=geography_match))

    if situation.keywords:

        def keyword_match(candidate: Candidate) -> bool:
            haystack = _text_fields(candidate)
            return any(kw in haystack for kw in situation.keywords)

        criteria.append(Criterion(name="keyword_match", predicate=keyword_match))

    return criteria