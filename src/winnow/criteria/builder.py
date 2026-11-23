"""Parse startup situations and bind template criteria."""

from __future__ import annotations

from collections.abc import Callable

from winnow.criteria.templates import TEMPLATES, build_from_template
from winnow.models import Candidate, Criteria, StartupSituation

_GOAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "design_partners": ("design partner", "design partners", "beta partner"),
    "first_revenue": ("first revenue", "first customer", "paying customer", "revenue"),
    "distribution_partners": (
        "distribution",
        "channel partner",
        "integration partner",
        "reseller",
    ),
    "investors": ("investor", "investment", "fundraise", "funding", "vc", "seed round"),
    "hires": ("hire", "hiring", "recruit", "headcount", "talent"),
    "community": ("community", "members", "ambassador", "evangelist"),
}


def parse_situation(data: dict) -> StartupSituation:
    """Build ``StartupSituation`` from a plain dict.

    If ``situation_type`` is present, it is prefixed onto ``goal`` as
    ``"{situation_type}: {goal}"`` so ``build_criteria`` can resolve the template
    when keyword inference is ambiguous.
    """
    stage = str(data.get("stage", ""))
    product = str(data.get("product", ""))
    goal = str(data.get("goal", ""))
    constraint = str(data.get("constraint", ""))
    segment = str(data.get("segment", ""))
    raw_channels = data.get("channels", ())
    if isinstance(raw_channels, str):
        channels = (raw_channels,) if raw_channels else ()
    else:
        channels = tuple(str(c) for c in raw_channels)

    situation_type = data.get("situation_type")
    if situation_type:
        prefix = str(situation_type).strip().lower()
        if not goal.lower().startswith(f"{prefix}:"):
            goal = f"{prefix}: {goal}".strip(": ")

    return StartupSituation(
        stage=stage,
        product=product,
        goal=goal,
        constraint=constraint,
        segment=segment,
        channels=channels,
    )


def _resolve_template_name(situation: StartupSituation) -> str:
    head = situation.goal.split(":", 1)[0].strip().lower()
    if head in TEMPLATES:
        return head

    haystack = " ".join(
        part.lower()
        for part in (situation.goal, situation.stage, situation.product, situation.constraint)
        if part
    )
    matches: list[str] = []
    for name, phrases in _GOAL_KEYWORDS.items():
        if any(phrase in haystack for phrase in phrases):
            matches.append(name)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous situation; matched templates {matches!r}. "
            "Set situation_type explicitly."
        )
    raise ValueError(
        "Unknown situation; set situation_type to one of: "
        + ", ".join(sorted(TEMPLATES))
    )


def build_criteria(
    situation: StartupSituation,
) -> tuple[list[Criteria], Callable[[Candidate], bool], str]:
    template_name = _resolve_template_name(situation)
    criteria, reachability = build_from_template(template_name, situation)
    return criteria, reachability, template_name