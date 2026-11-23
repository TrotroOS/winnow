"""Pure binary filter — criteria predicates only; reachability applied separately."""

from __future__ import annotations

from winnow.models import Candidate, Criterion
from winnow.reachability import ReachabilityPredicate


def passes_criteria(candidate: Candidate, criteria: list[Criterion]) -> bool:
    """All criteria must pass; returns bool only."""
    return all(c.predicate(candidate) for c in criteria)


def is_possible(
    candidate: Candidate,
    criteria: list[Criterion],
    reachable: ReachabilityPredicate,
) -> bool:
    """Candidate is POSSIBLE iff criteria pass and reachability gate passes."""
    if not passes_criteria(candidate, criteria):
        return False
    return reachable(candidate)


def partition_possible(
    candidates: list[Candidate],
    criteria: list[Criterion],
    reachable: ReachabilityPredicate,
) -> tuple[list[Candidate], int]:
    """Split into POSSIBLE list and noise_dropped count. NOISE is not retained."""
    possible: list[Candidate] = []
    noise_dropped = 0
    for candidate in candidates:
        if is_possible(candidate, criteria, reachable):
            possible.append(candidate)
        else:
            noise_dropped += 1
    return possible, noise_dropped