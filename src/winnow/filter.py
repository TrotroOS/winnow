"""Binary filter and reachability gate (POSSIBLE vs NOISE only)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from inspect import signature

from winnow.models import Candidate, Criteria

# Reachable if any of these contact paths is non-empty (after strip).
REACHABILITY_KEYS: tuple[str, ...] = ("email", "linkedin", "dm")


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


def evaluate(
    candidate: Candidate,
    criteria: Sequence[Criteria],
    *,
    now: datetime | None = None,
) -> bool:
    """True only if every predicate is True. Short-circuits on first False.

    Predicates run cheapest-first (Criteria.cost). Cost is ordering only.
    """
    for criterion in _order_criteria(criteria):
        if not _invoke_predicate(criterion.predicate, candidate, now=now):
            return False
    return True


def reachable(candidate: Candidate) -> bool:
    """Hard gate: non-empty email, linkedin, or dm in contacts."""
    for key in REACHABILITY_KEYS:
        value = candidate.contacts.get(key)
        if isinstance(value, str) and value.strip():
            return True
    return False


def apply_filter(
    candidates: Sequence[Candidate],
    criteria: Sequence[Criteria],
    reachability: Callable[[Candidate], bool],
    *,
    now: datetime | None = None,
) -> tuple[list[Candidate], int]:
    """Return (possible, noise_dropped). NOISE is not returned or retained."""
    possible: list[Candidate] = []
    noise_dropped = 0

    for candidate in candidates:
        if not reachability(candidate):
            noise_dropped += 1
            continue
        if not evaluate(candidate, criteria, now=now):
            noise_dropped += 1
            continue
        possible.append(candidate)

    return possible, noise_dropped