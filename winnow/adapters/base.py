"""Abstract source adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SourceAdapter(ABC):
    """Cheapest-to-expensive sources implement fetch_raw."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable source identifier."""

    @property
    @abstractmethod
    def cost_rank(self) -> int:
        """Lower is cheaper; router sorts ascending."""

    @abstractmethod
    def fetch_raw(self) -> list[dict[str, Any]]:
        """Return raw records from this source (may involve I/O in real adapters)."""