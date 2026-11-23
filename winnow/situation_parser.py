"""Parse startup situation text into a structured Situation (pure, no I/O)."""

from __future__ import annotations

import re
from typing import Any

from winnow.models import Situation

_SITUATION_TYPES: frozenset[str] = frozenset(
    {
        "launch",
        "fundraise",
        "pivot",
        "churn",
        "expansion",
        "pmf",
        "hiring",
        "sales",
        "partnerships",
        "research",
        "unknown",
    }
)

_SECTOR_HINTS: frozenset[str] = frozenset(
    {
        "fintech",
        "health",
        "healthtech",
        "b2b",
        "b2c",
        "saas",
        "ai",
        "ml",
        "devtools",
        "edtech",
        "proptech",
        "climate",
        "crypto",
        "marketplace",
        "enterprise",
        "consumer",
    }
)

_ROLE_HINTS: frozenset[str] = frozenset(
    {
        "cto",
        "ceo",
        "cfo",
        "coo",
        "founder",
        "co-founder",
        "cofounder",
        "pm",
        "product",
        "engineer",
        "developer",
        "designer",
        "sales",
        "marketing",
        "ops",
        "operator",
        "vp",
        "head",
        "lead",
    }
)

_GEO_PATTERN = re.compile(
    r"\b(?:in|across|within|based in|targeting)\s+([A-Za-z][A-Za-z\s\-]{1,40})",
    re.IGNORECASE,
)
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def _normalize_phrase(value: str) -> str:
    return " ".join(value.lower().split())


def parse_situation_text(text: str) -> Situation:
    """Parse free-text startup situation into structured hints."""
    cleaned = text.strip()
    if not cleaned:
        return Situation(
            situation_type="unknown",
            sector_hints=(),
            role_hints=(),
            geography=None,
            keywords=(),
        )

    tokens = _tokens(cleaned)
    situation_type = "unknown"
    for token in tokens:
        if token in _SITUATION_TYPES:
            situation_type = token
            break
    if situation_type == "unknown" and tokens:
        situation_type = tokens[0]

    sector_hints = tuple(sorted({t for t in tokens if t in _SECTOR_HINTS}))
    role_hints = tuple(sorted({t for t in tokens if t in _ROLE_HINTS}))

    geography: str | None = None
    geo_match = _GEO_PATTERN.search(cleaned)
    if geo_match:
        geography = _normalize_phrase(geo_match.group(1))

    consumed = {situation_type, *sector_hints, *role_hints}
    keywords = tuple(t for t in tokens if t not in consumed and len(t) > 2)

    return Situation(
        situation_type=situation_type,
        sector_hints=sector_hints,
        role_hints=role_hints,
        geography=geography,
        keywords=keywords,
    )


def parse_situation(raw: str | dict[str, Any]) -> Situation:
    """Parse a situation from user text or a structured dict."""
    if isinstance(raw, dict):
        return Situation(
            situation_type=str(raw.get("type") or raw.get("situation_type") or "unknown"),
            sector_hints=tuple(raw.get("sector_hints") or ()),
            role_hints=tuple(raw.get("role_hints") or ()),
            geography=raw.get("geography"),
            keywords=tuple(raw.get("keywords") or ()),
        )
    if isinstance(raw, str):
        return parse_situation_text(raw)
    return Situation(
        situation_type="unknown",
        sector_hints=(),
        role_hints=(),
        geography=None,
        keywords=(),
    )