"""Reachability hard gate — separate from binary criteria predicates."""

from __future__ import annotations

from collections.abc import Callable

from winnow.models import Candidate


def default_reachable(candidate: Candidate) -> bool:
    """True when the candidate has at least one contact channel."""
    if not candidate.contacts:
        return False
    for value in candidate.contacts.values():
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                return True
            continue
        if value:
            return True
    return False


ReachabilityPredicate = Callable[[Candidate], bool]