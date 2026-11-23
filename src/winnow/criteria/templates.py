"""Template library: situation type -> criteria + reachability gate."""

from __future__ import annotations

from collections.abc import Callable

from winnow.criteria import predicates as p
from winnow.filter import reachable
from winnow.models import Candidate, Criteria, StartupSituation

TemplateFn = Callable[
    [StartupSituation],
    tuple[list[Criteria], Callable[[Candidate], bool]],
]


def _design_partners(
    situation: StartupSituation,
) -> tuple[list[Criteria], Callable[[Candidate], bool]]:
    return (
        [
            Criteria(
                name="design_partner_open",
                predicate=p.signal_is_yes("design_partner_open"),
                cost=1,
            ),
            Criteria(
                name="org_in_segment",
                predicate=p.org_in_segment(situation.segment),
                cost=2,
            ),
            Criteria(
                name="product_role",
                predicate=p.role_matches(("product", "engineering", "founder", "cto")),
                cost=3,
            ),
            Criteria(
                name="recent_activity",
                predicate=p.has_signal_within(90),
                cost=5,
            ),
        ],
        reachable,
    )


def _first_revenue(
    situation: StartupSituation,
) -> tuple[list[Criteria], Callable[[Candidate], bool]]:
    _ = situation
    return (
        [
            Criteria(
                name="revenue_ready",
                predicate=p.signal_is_yes("revenue_ready"),
                cost=1,
            ),
            Criteria(
                name="recent_activity",
                predicate=p.has_signal_within(60),
                cost=2,
            ),
            Criteria(
                name="decision_maker",
                predicate=p.role_matches(
                    ("founder", "ceo", "head", "director", "vp", "owner")
                ),
                cost=3,
            ),
        ],
        reachable,
    )


def _distribution_partners(
    situation: StartupSituation,
) -> tuple[list[Criteria], Callable[[Candidate], bool]]:
    return (
        [
            Criteria(
                name="has_partner_page",
                predicate=p.has_partner_page(),
                cost=1,
            ),
            Criteria(
                name="lists_complementary_product",
                predicate=p.lists_complementary_product(situation.product),
                cost=2,
            ),
            Criteria(
                name="org_in_segment",
                predicate=p.org_in_segment(situation.segment),
                cost=4,
            ),
        ],
        reachable,
    )


def _investors(
    situation: StartupSituation,
) -> tuple[list[Criteria], Callable[[Candidate], bool]]:
    return (
        [
            Criteria(
                name="invests_in_sector",
                predicate=p.invests_in_sector(situation.segment),
                cost=1,
            ),
            Criteria(
                name="investor_role",
                predicate=p.role_matches(
                    ("investor", "partner", "gp", "vc", "angel", "principal")
                ),
                cost=2,
            ),
            Criteria(
                name="recent_activity",
                predicate=p.has_signal_within(120),
                cost=5,
            ),
        ],
        reachable,
    )


def _hires(
    situation: StartupSituation,
) -> tuple[list[Criteria], Callable[[Candidate], bool]]:
    role_hint = situation.product or situation.segment or "engineer"
    return (
        [
            Criteria(
                name="hiring",
                predicate=p.signal_is_yes("hiring"),
                cost=1,
            ),
            Criteria(
                name="open_role_match",
                predicate=p.hiring_for_role(role_hint),
                cost=2,
            ),
            Criteria(
                name="org_in_segment",
                predicate=p.org_in_segment(situation.segment),
                cost=3,
            ),
        ],
        reachable,
    )


def _community(
    situation: StartupSituation,
) -> tuple[list[Criteria], Callable[[Candidate], bool]]:
    _ = situation
    return (
        [
            Criteria(
                name="community_member",
                predicate=p.signal_is_yes("community_member"),
                cost=1,
            ),
            Criteria(
                name="recent_activity",
                predicate=p.has_signal_within(30),
                cost=2,
            ),
        ],
        reachable,
    )


def _segment_expansion(
    situation: StartupSituation,
) -> tuple[list[Criteria], Callable[[Candidate], bool]]:
    return (
        [
            Criteria(
                name="segment_expansion_open",
                predicate=p.signal_is_yes("segment_expansion_open"),
                cost=1,
            ),
            Criteria(
                name="org_in_segment",
                predicate=p.org_in_segment(situation.segment),
                cost=2,
            ),
            Criteria(
                name="decision_maker",
                predicate=p.role_matches(
                    ("founder", "ceo", "cto", "vp", "director", "head")
                ),
                cost=3,
            ),
            Criteria(
                name="recent_activity",
                predicate=p.has_signal_within(60),
                cost=4,
            ),
        ],
        reachable,
    )


TEMPLATES: dict[str, TemplateFn] = {
    "design_partners": _design_partners,
    "first_revenue": _first_revenue,
    "distribution_partners": _distribution_partners,
    "investors": _investors,
    "hires": _hires,
    "community": _community,
    "segment_expansion": _segment_expansion,
}


def build_from_template(
    template_name: str, situation: StartupSituation
) -> tuple[list[Criteria], Callable[[Candidate], bool]]:
    key = template_name.strip().lower()
    try:
        factory = TEMPLATES[key]
    except KeyError as exc:
        known = ", ".join(sorted(TEMPLATES))
        raise ValueError(f"Unknown template {template_name!r}; known: {known}") from exc
    return factory(situation)