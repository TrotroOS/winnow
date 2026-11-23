"""Opt-in generative criteria: vocabulary-bound SELECT+PARAMETERIZE proposals.

Disabled unless ``WINNOW_ALLOW_GENERATIVE=1``. Proposals may only reference
predicates from the registry (existing ``predicates`` factories). Any
float / score / weight field rejects the whole proposal and logs a violation.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from winnow.criteria import predicates as p
from winnow.filter import reachable
from winnow.models import Candidate, Criteria, StartupSituation

logger = logging.getLogger(__name__)

_FORBIDDEN_NAME = re.compile(
    r"(score|weight|confidence|priority|rank|fit|quality|probability)",
    re.IGNORECASE,
)

PredicateFactory = Callable[..., Callable[[Candidate], bool]]

_VOCABULARY: dict[str, PredicateFactory] = {
    "has_signal_within": p.has_signal_within,
    "role_matches": p.role_matches,
    "org_in_segment": p.org_in_segment,
    "invests_in_sector": p.invests_in_sector,
    "has_partner_page": p.has_partner_page,
    "lists_complementary_product": p.lists_complementary_product,
    "signal_is_yes": p.signal_is_yes,
    "hiring_for_role": p.hiring_for_role,
    "collected_within": p.collected_within,
}


def vocabulary_keys() -> frozenset[str]:
    """Registered predicate factory names (existing predicates only)."""
    return frozenset(_VOCABULARY)


def allow_generative() -> bool:
    """True when ``WINNOW_ALLOW_GENERATIVE`` is set to a truthy value."""
    raw = os.environ.get("WINNOW_ALLOW_GENERATIVE", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class PredicateSelection:
    """One named criterion: SELECT vocabulary entry + PARAMETERIZE args."""

    name: str
    select: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    cost: int = 5


@dataclass(frozen=True, slots=True)
class CriteriaProposal:
    """List of bool predicate selections (no scores)."""

    selections: tuple[PredicateSelection, ...] = ()


class ProposalRejected(ValueError):
    """Whole proposal rejected (binary-only violation)."""

    def __init__(self, message: str, *, violations: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.violations = violations


def _scan_forbidden(value: Any, path: str, violations: list[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        violations.append(f"{path}: float value {value!r}")
        return
    if isinstance(value, int):
        return
    if isinstance(value, str):
        if _FORBIDDEN_NAME.search(value):
            violations.append(f"{path}: forbidden token in string {value!r}")
        return
    if value is None:
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_s = str(key)
            if _FORBIDDEN_NAME.search(key_s):
                violations.append(f"{path}.{key_s}: forbidden key")
            _scan_forbidden(child, f"{path}.{key_s}", violations)
        return
    if isinstance(value, (list, tuple)):
        for idx, child in enumerate(value):
            _scan_forbidden(child, f"{path}[{idx}]", violations)
        return
    violations.append(f"{path}: unsupported type {type(value).__name__}")


def validate_proposal(proposal: CriteriaProposal) -> None:
    """Raise ``ProposalRejected`` if any score/float/weight appears anywhere."""
    violations: list[str] = []
    for idx, sel in enumerate(proposal.selections):
        base = f"selections[{idx}]"
        if _FORBIDDEN_NAME.search(sel.name):
            violations.append(f"{base}.name: forbidden token")
        if sel.select not in _VOCABULARY:
            violations.append(f"{base}.select: unknown predicate {sel.select!r}")
        if isinstance(sel.cost, float):
            violations.append(f"{base}.cost: float cost")
        if _FORBIDDEN_NAME.search(sel.select):
            violations.append(f"{base}.select: forbidden token")
        _scan_forbidden(dict(sel.parameters), f"{base}.parameters", violations)
    if violations:
        for line in violations:
            logger.warning("generative proposal violation: %s", line)
        raise ProposalRejected(
            "generative proposal rejected (binary-only violation)",
            violations=tuple(violations),
        )


def _bind_factory(select: str, parameters: Mapping[str, Any]) -> Callable[[Candidate], bool]:
    factory = _VOCABULARY[select]
    if not parameters:
        return factory()  # type: ignore[call-arg]
    kwargs = dict(parameters)
    return factory(**kwargs)  # type: ignore[call-arg]


def materialize_proposal(
    proposal: CriteriaProposal,
    *,
    validate: bool = True,
) -> list[Criteria]:
    """Turn a validated proposal into executable ``Criteria`` (bool predicates)."""
    if validate:
        validate_proposal(proposal)
    criteria: list[Criteria] = []
    for sel in proposal.selections:
        predicate = _bind_factory(sel.select, sel.parameters)
        criteria.append(
            Criteria(
                name=sel.name,
                predicate=predicate,
                cost=int(sel.cost),
            )
        )
    return criteria


def proposal_to_json(proposal: CriteriaProposal) -> str:
    payload = {
        "selections": [
            {
                "name": s.name,
                "select": s.select,
                "parameters": dict(s.parameters),
                "cost": s.cost,
            }
            for s in proposal.selections
        ]
    }
    return json.dumps(payload, sort_keys=True)


def proposal_from_json(raw: str) -> CriteriaProposal:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ProposalRejected("proposal root must be object")
    selections_raw = data.get("selections", ())
    if not isinstance(selections_raw, list):
        raise ProposalRejected("selections must be a list")
    selections: list[PredicateSelection] = []
    for item in selections_raw:
        if not isinstance(item, dict):
            raise ProposalRejected("each selection must be object")
        selections.append(
            PredicateSelection(
                name=str(item["name"]),
                select=str(item["select"]),
                parameters=dict(item.get("parameters") or {}),
                cost=int(item.get("cost", 5)),
            )
        )
    return CriteriaProposal(selections=tuple(selections))


def materialize_from_json(raw: str) -> list[Criteria]:
    return materialize_proposal(proposal_from_json(raw))


@runtime_checkable
class CriteriaProposer(Protocol):
    """Injectable proposer (tests supply fakes; production may use LLM backend)."""

    def propose(self, situation: StartupSituation) -> CriteriaProposal:
        """Return SELECT+PARAMETERIZE selections only (no scores)."""


class HeuristicCriteriaProposer:
    """Deterministic proposer for tests and dry runs without an LLM."""

    def propose(self, situation: StartupSituation) -> CriteriaProposal:
        segment = situation.segment or "general"
        product = situation.product or segment
        return CriteriaProposal(
            selections=(
                PredicateSelection(
                    name="org_in_segment",
                    select="org_in_segment",
                    parameters={"segment": segment},
                    cost=2,
                ),
                PredicateSelection(
                    name="recent_activity",
                    select="has_signal_within",
                    parameters={"days": 60},
                    cost=3,
                ),
                PredicateSelection(
                    name="complementary",
                    select="lists_complementary_product",
                    parameters={"product": product},
                    cost=4,
                ),
            )
        )


def propose_criteria(
    situation: StartupSituation,
    *,
    proposer: CriteriaProposer | None = None,
) -> CriteriaProposal:
    """Propose criteria when generative mode is allowed; else raise."""
    if not allow_generative():
        raise RuntimeError(
            "generative criteria disabled; set WINNOW_ALLOW_GENERATIVE=1"
        )
    impl = proposer or HeuristicCriteriaProposer()
    proposal = impl.propose(situation)
    validate_proposal(proposal)
    return proposal


def build_from_proposal(
    proposal: CriteriaProposal,
) -> tuple[list[Criteria], Callable[[Candidate], bool]]:
    """Materialize criteria + standard reachability gate."""
    return materialize_proposal(proposal), reachable


def load_criteria_version_for_run(
    store: Any,
    criteria_version_id: int,
) -> tuple[list[Criteria], Callable[[Candidate], bool], str]:
    """Load stored proposal; generated rows must be operator-approved first."""
    version = store.get_criteria_version(criteria_version_id)
    if version is None:
        raise ValueError(f"unknown criteria_version id={criteria_version_id}")
    if version["generated"] and not version["approved"]:
        raise ValueError(
            f"criteria_version {criteria_version_id} is generated but not approved; "
            "run: python -m winnow.run approve-criteria --id "
            f"{criteria_version_id}"
        )
    raw = version.get("proposal_json") or ""
    if not raw:
        raise ValueError(
            f"criteria_version {criteria_version_id} has no stored proposal"
        )
    proposal = proposal_from_json(raw)
    criteria, reach = build_from_proposal(proposal)
    template_name = str(version.get("template_name") or "generated")
    return criteria, reach, template_name


def store_generative_proposal(
    store: Any,
    situation: StartupSituation,
    *,
    proposer: CriteriaProposer | None = None,
    template_name: str = "generated",
) -> int:
    """Validate, materialize names, persist unapproved ``generated`` row."""
    proposal = propose_criteria(situation, proposer=proposer)
    names = tuple(s.name for s in proposal.selections)
    return int(
        store.record_criteria_version(
            template_name,
            names,
            generated=True,
            approved=False,
            proposal_json=proposal_to_json(proposal),
        )
    )