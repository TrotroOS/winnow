"""Route to source adapters, cheapest first.

Cost order (lower ``cost_rank`` runs first):
  0 — in-memory ``FixtureSourceAdapter`` (tests / zero-cost dry-runs)
  1 — ``CsvDirectorySourceAdapter`` (local files, ``WINNOW_CSV_SOURCE_DIR``)
  2 — ``GitHubSearchSourceAdapter`` (API, only when ``WINNOW_GITHUB_TOKEN`` is set)
"""

from __future__ import annotations

import os
from typing import Any

from winnow.adapters.base import SourceAdapter
from winnow.adapters.csv_directory import CsvDirectorySourceAdapter
from winnow.adapters.github_search import GitHubSearchSourceAdapter

COST_RANK_FIXTURE = 0
COST_RANK_CSV = 1
COST_RANK_GITHUB = 2


def order_adapters(adapters: list[SourceAdapter]) -> list[SourceAdapter]:
    """Return adapters sorted by cost_rank ascending."""
    return sorted(adapters, key=lambda a: a.cost_rank)


def fetch_all_ordered(adapters: list[SourceAdapter]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Fetch from each adapter in cost order."""
    ordered = order_adapters(adapters)
    return [(a.name, a.fetch_raw()) for a in ordered]


def resolve_adapters_from_env(
    *,
    github_query: str | None = None,
    extra: list[SourceAdapter] | None = None,
) -> list[SourceAdapter]:
    """Build runtime adapter list from environment (no fixture unless passed in ``extra``)."""
    adapters: list[SourceAdapter] = list(extra or [])

    csv_dir = os.environ.get("WINNOW_CSV_SOURCE_DIR")
    if csv_dir:
        adapters.append(CsvDirectorySourceAdapter(csv_dir, cost_rank=COST_RANK_CSV))

    token = os.environ.get("WINNOW_GITHUB_TOKEN")
    if token:
        adapters.append(
            GitHubSearchSourceAdapter(
                token=token,
                query=github_query or "startup",
                cost_rank=COST_RANK_GITHUB,
            )
        )

    return adapters