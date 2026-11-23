"""In-memory fixture adapter for tests and zero-cost runs."""

from __future__ import annotations

from typing import Any

from winnow.adapters.base import SourceAdapter


class FixtureSourceAdapter(SourceAdapter):
    """Cheap in-memory source; implements SourceAdapter protocol."""

    def __init__(self, name: str, records: list[dict[str, Any]], cost_rank: int = 0) -> None:
        self._name = name
        self._records = list(records)
        self._cost_rank = cost_rank

    @property
    def name(self) -> str:
        return self._name

    @property
    def cost_rank(self) -> int:
        return self._cost_rank

    def fetch_raw(self) -> list[dict[str, Any]]:
        return list(self._records)