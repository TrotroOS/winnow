"""Source router: cheapest adapters first.

The router **only orders** registered ``SourceAdapter`` instances by
``cost_per_call`` (ascending). It does **not** invoke ``search``.

Paid sources must not be called for enrichment until the caller has run the
binary filter on candidates from cheaper sources and explicitly chooses to
invoke a paid adapter's ``search`` (enrichment happens only after POSSIBLE is
known — see project spec).
"""

from __future__ import annotations

from collections.abc import Sequence

from winnow.models import Criteria, StartupSituation
from winnow.sources.adapter import SourceAdapter
from winnow.sources.registry import list_adapters


def route(
    situation: StartupSituation,
    criteria: Sequence[Criteria],
) -> list[SourceAdapter]:
    """Return adapters cheapest-first for this run.

    ``situation`` and ``criteria`` are reserved for future source selection;
    today all registered adapters are included, sorted by ``cost_per_call``.
    """
    del situation, criteria  # selection hooks later; ordering only today
    return sorted(list_adapters(), key=lambda a: (a.cost_per_call, a.name))