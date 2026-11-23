"""Route to source adapters, cheapest first."""

from __future__ import annotations

from typing import Any

from winnow.adapters.base import SourceAdapter


def order_adapters(adapters: list[SourceAdapter]) -> list[SourceAdapter]:
    """Return adapters sorted by cost_rank ascending."""
    return sorted(adapters, key=lambda a: a.cost_rank)


def fetch_all_ordered(adapters: list[SourceAdapter]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Fetch from each adapter in cost order."""
    ordered = order_adapters(adapters)
    return [(a.name, a.fetch_raw()) for a in ordered]