from __future__ import annotations

from typing import Protocol

from winnow.models import Candidate


class SourceAdapter(Protocol):
    name: str
    cost_per_call: float

    def search(self, queries: list[str], limit: int) -> list[Candidate]: ...