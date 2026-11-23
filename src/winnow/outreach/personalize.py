"""Determine ``matched_signal`` for outreach copy (no scoring)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from inspect import signature

from winnow.models import Candidate, Criteria


class MatchedSignalError(ValueError):
    """Cannot build outreach copy without a personalization hook."""


def _order_criteria(criteria: Sequence[Criteria]) -> list[Criteria]:
    return sorted(criteria, key=lambda c: c.cost)


def _invoke_predicate(
    predicate: Callable[..., bool],
    candidate: Candidate,
    *,
    now: datetime | None,
) -> bool:
    params = signature(predicate).parameters
    if now is not None and "now" in params:
        return predicate(candidate, now=now)
    return predicate(candidate)


def _signal_text(candidate: Candidate, key: str) -> str | None:
    raw = candidate.signals.get(key, "")
    text = raw.strip() if isinstance(raw, str) else ""
    return text or None


def _activity_description(candidate: Candidate) -> str | None:
    days = _signal_text(candidate, "activity_days")
    if not days:
        return None
    return f"recently active ({days} days)"


def _role_description(candidate: Candidate) -> str | None:
    role = candidate.role.strip()
    return role or None


def _org_or_segment(candidate: Candidate) -> str | None:
    segment = _signal_text(candidate, "segment")
    if segment:
        return f"focus on {segment}"
    org = candidate.org.strip()
    return org or None


def _investment_focus(candidate: Candidate) -> str | None:
    for key in ("invests_in", "sector"):
        text = _signal_text(candidate, key)
        if text:
            return f"invests in {text}"
    return None


def _complementary_product(candidate: Candidate) -> str | None:
    text = _signal_text(candidate, "complementary_product")
    if text:
        return f"lists {text}"
    if _signal_text(candidate, "lists_complementary_product"):
        return "lists complementary integrations"
    return None


def _hiring_roles(candidate: Candidate) -> str | None:
    roles = _signal_text(candidate, "open_roles")
    if roles:
        return f"hiring for {roles}"
    if _signal_text(candidate, "hiring"):
        return "actively hiring"
    return None


def _yes_signal_phrase(key: str, phrase: str) -> Callable[[Candidate], str | None]:
    def describe(candidate: Candidate) -> str | None:
        text = _signal_text(candidate, key)
        if not text:
            return None
        if text.lower() in {"yes", "true", "1"}:
            return phrase
        return text

    return describe


DESCRIPTION_BY_CRITERION: dict[str, Callable[[Candidate], str | None]] = {
    "design_partner_open": _yes_signal_phrase(
        "design_partner_open", "open to design partnerships"
    ),
    "org_in_segment": _org_or_segment,
    "product_role": _role_description,
    "recent_activity": _activity_description,
    "revenue_ready": _yes_signal_phrase("revenue_ready", "ready to adopt for revenue"),
    "decision_maker": _role_description,
    "has_partner_page": _yes_signal_phrase("partner_page", "runs a partner program"),
    "lists_complementary_product": _complementary_product,
    "invests_in_sector": _investment_focus,
    "investor_role": _role_description,
    "hiring": _yes_signal_phrase("hiring", "currently hiring"),
    "open_role_match": _hiring_roles,
    "community_member": _yes_signal_phrase("community_member", "active in the community"),
    "segment_expansion_open": _yes_signal_phrase(
        "segment_expansion_open", "open to segment expansion conversations"
    ),
}


def matched_signal(
    candidate: Candidate,
    criteria: Sequence[Criteria],
    *,
    now: datetime | None = None,
) -> str:
    """First passing criterion (cheapest-first) with a non-empty signal description."""
    for criterion in _order_criteria(criteria):
        if not _invoke_predicate(criterion.predicate, candidate, now=now):
            continue
        describer = DESCRIPTION_BY_CRITERION.get(criterion.name)
        if describer is None:
            continue
        text = describer(candidate)
        if text and text.strip():
            return text.strip()
    raise MatchedSignalError(
        f"cannot determine matched_signal for candidate {candidate.id!r}"
    )