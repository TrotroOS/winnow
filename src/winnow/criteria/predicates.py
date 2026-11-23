"""Pure bool predicates over ``Candidate`` (no I/O).

Expected ``signals`` keys (string values unless noted):

- ``activity_days``: days since last relevant activity (integer as string)
- ``segment``: market / ICP segment label
- ``invests_in``: sectors or stages the investor backs
- ``sector``: organization sector (fallback for investor matching)
- ``partner_page``: ``yes`` when org publishes a partner program page
- ``has_partner_page``: alias for ``partner_page``
- ``complementary_product``: product name or ``yes`` when they list partners
- ``lists_complementary_product``: ``yes`` when partner/integration page exists
- ``design_partner_open``: ``yes`` when accepting design partners
- ``revenue_ready``: ``yes`` when candidate can pay / adopt for revenue
- ``community_member``: ``yes`` when active in target community
- ``hiring``: ``yes`` when org is actively hiring
- ``open_roles``: comma-separated roles being hired
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone

from winnow.models import Candidate


def _signal(candidate: Candidate, key: str) -> str:
    value = candidate.signals.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def _is_yes(candidate: Candidate, key: str) -> bool:
    return _signal(candidate, key).lower() in {"yes", "true", "1"}


def has_signal_within(days: int, *, signal_key: str = "activity_days") -> Callable[..., bool]:
    """True when ``signals[signal_key]`` is an integer day count <= *days*."""

    def predicate(candidate: Candidate, *, now: datetime | None = None) -> bool:
        raw = _signal(candidate, signal_key)
        if not raw:
            return False
        try:
            elapsed = int(raw)
        except ValueError:
            return False
        return elapsed <= days

    return predicate


def role_matches(roles: Sequence[str]) -> Callable[[Candidate], bool]:
    """True when ``candidate.role`` contains any *roles* (case-insensitive)."""
    normalized = tuple(r.lower() for r in roles)

    def predicate(candidate: Candidate) -> bool:
        role = candidate.role.lower()
        return any(r in role or role in r for r in normalized)

    return predicate


def org_in_segment(segment: str) -> Callable[[Candidate], bool]:
    """True when ``signals['segment']`` or org name contains *segment*."""

    needle = segment.lower()

    def predicate(candidate: Candidate) -> bool:
        if needle in candidate.org.lower():
            return True
        return needle in _signal(candidate, "segment").lower()

    return predicate


def invests_in_sector(sector: str) -> Callable[[Candidate], bool]:
    """True when ``signals['invests_in']`` or ``signals['sector']`` mentions *sector*."""

    needle = sector.lower()

    def predicate(candidate: Candidate) -> bool:
        for key in ("invests_in", "sector"):
            hay = _signal(candidate, key).lower()
            if needle and needle in hay:
                return True
        return False

    return predicate


def has_partner_page() -> Callable[[Candidate], bool]:
    """True when ``partner_page`` or ``has_partner_page`` is yes."""

    def predicate(candidate: Candidate) -> bool:
        return _is_yes(candidate, "partner_page") or _is_yes(candidate, "has_partner_page")

    return predicate


def lists_complementary_product(product: str) -> Callable[[Candidate], bool]:
    """True when complementary product signal matches *product* or is yes."""

    needle = product.lower()

    def predicate(candidate: Candidate) -> bool:
        if _is_yes(candidate, "lists_complementary_product"):
            return True
        comp = _signal(candidate, "complementary_product").lower()
        if not comp:
            return False
        if comp in {"yes", "true", "1"}:
            return bool(needle)
        return needle in comp or comp in needle

    return predicate


def signal_is_yes(key: str) -> Callable[[Candidate], bool]:
    def predicate(candidate: Candidate) -> bool:
        return _is_yes(candidate, key)

    return predicate


def hiring_for_role(role_hint: str) -> Callable[[Candidate], bool]:
    """True when ``hiring`` is yes and ``open_roles`` contains *role_hint*."""

    hint = role_hint.lower()

    def predicate(candidate: Candidate) -> bool:
        if not _is_yes(candidate, "hiring"):
            return False
        roles = _signal(candidate, "open_roles").lower()
        return hint in roles if roles else True

    return predicate


def collected_within(days: int) -> Callable[..., bool]:
    """True when ``candidate.collected_at`` is within *days* of *now* (cheap date check)."""

    def predicate(candidate: Candidate, *, now: datetime | None = None) -> bool:
        reference = now or datetime.now(timezone.utc)
        if candidate.collected_at.tzinfo is None:
            collected = candidate.collected_at.replace(tzinfo=timezone.utc)
        else:
            collected = candidate.collected_at
        return collected >= reference - timedelta(days=days)

    return predicate