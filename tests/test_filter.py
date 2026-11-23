from __future__ import annotations

from winnow.binary_filter import is_possible, partition_possible, passes_criteria
from winnow.criteria_builder import build_criteria
from winnow.models import Candidate, Situation
from winnow.reachability import default_reachable


def test_passes_criteria_org_required(sample_candidates: list[Candidate]) -> None:
    criteria = build_criteria(Situation("early_b2b", (), (), None, ()))
    assert passes_criteria(sample_candidates[0], criteria)
    assert not passes_criteria(sample_candidates[1], criteria)


def test_reachability_is_separate_gate(sample_candidates: list[Candidate]) -> None:
    criteria = build_criteria(Situation("early_b2b", (), (), None, ()))
    assert not is_possible(sample_candidates[2], criteria, default_reachable)


def test_partition_drops_noise_not_stored(sample_candidates: list[Candidate]) -> None:
    criteria = build_criteria(Situation("early_b2b", (), (), None, ()))
    # Partition operates on already-deduped lists (dedupe is a separate stage).
    unique = sample_candidates[:3]
    possible, noise_dropped = partition_possible(
        unique, criteria, default_reachable
    )
    assert len(possible) == 1
    assert possible[0].id == "c1"
    assert noise_dropped == 2