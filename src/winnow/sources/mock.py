from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from winnow.models import Candidate

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"


class MockSource:
    """Deterministic search results from ``tests/fixtures/*.json``."""

    name: str = "mock"
    cost_per_call: float = 0.0

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = fixtures_dir or _FIXTURES_DIR
        self._candidates: tuple[Candidate, ...] | None = None

    def _load(self) -> tuple[Candidate, ...]:
        if self._candidates is not None:
            return self._candidates

        loaded: list[Candidate] = []
        if self._fixtures_dir.is_dir():
            for path in sorted(self._fixtures_dir.glob("*.json")):
                raw = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, list):
                    msg = f"fixture {path.name} must be a JSON array"
                    raise ValueError(msg)
                for item in raw:
                    collected_at = item["collected_at"]
                    if isinstance(collected_at, str):
                        collected_at = datetime.fromisoformat(collected_at)
                    loaded.append(
                        Candidate(
                            id=item["id"],
                            name=item["name"],
                            org=item["org"],
                            role=item["role"],
                            signals=dict(item.get("signals", {})),
                            contacts=dict(item.get("contacts", {})),
                            source=item.get("source", self.name),
                            collected_at=collected_at,
                        )
                    )

        loaded.sort(key=lambda c: c.id)
        self._candidates = tuple(loaded)
        return self._candidates

    def search(self, queries: list[str], limit: int) -> list[Candidate]:
        """Return up to ``limit`` fixture candidates (queries ignored for mock)."""
        del queries  # mock is deterministic; no query semantics
        pool = self._load()
        if limit <= 0:
            return []
        return list(pool[:limit])