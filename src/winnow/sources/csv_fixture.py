"""Fixture-backed source returning raw dict payloads (CSV or JSON)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures"


class CsvFixtureSource:
    """Load ``tests/fixtures/*.csv`` and optional JSON; ``search`` returns raw dicts."""

    name: str = "csv_fixture"
    cost_per_call: float = 0.01

    def __init__(
        self,
        fixtures_dir: Path | None = None,
        *,
        csv_name: str = "segment_expansion_enterprise.csv",
        json_name: str | None = "segment_expansion_enterprise.json",
    ) -> None:
        self._fixtures_dir = fixtures_dir or _FIXTURES_DIR
        self._csv_path = self._fixtures_dir / csv_name
        self._json_path = (
            self._fixtures_dir / json_name if json_name else None
        )
        self._rows: list[dict[str, object]] | None = None

    def _load(self) -> list[dict[str, object]]:
        if self._rows is not None:
            return self._rows

        rows: list[dict[str, object]] = []
        if self._csv_path.is_file():
            with self._csv_path.open(newline="", encoding="utf-8") as handle:
                for item in csv.DictReader(handle):
                    rows.append(_row_from_mapping(item, source=self.name))
        elif self._json_path and self._json_path.is_file():
            raw = json.loads(self._json_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        rows.append(_row_from_mapping(item, source=self.name))
        rows.sort(key=lambda r: str(r.get("id", "")))
        self._rows = rows
        return rows

    def search(self, queries: list[str], limit: int) -> list[dict[str, object]]:
        del queries
        pool = self._load()
        if limit <= 0:
            return []
        return [dict(r) for r in pool[:limit]]


def _row_from_mapping(item: dict[str, str], *, source: str) -> dict[str, object]:
    signals = {
        k: item[k]
        for k in (
            "segment",
            "activity_days",
            "segment_expansion_open",
            "community_member",
        )
        if k in item and item[k]
    }
    contacts: dict[str, str] = {}
    if item.get("email"):
        contacts["email"] = item["email"]
    if item.get("linkedin"):
        contacts["linkedin"] = item["linkedin"]
    collected = item.get("collected_at", "2026-01-05T10:00:00+00:00")
    return {
        "id": item.get("id", ""),
        "name": item.get("name", ""),
        "org": item.get("org", ""),
        "role": item.get("role", ""),
        "signals": signals,
        "contacts": contacts,
        "source": item.get("source", source),
        "collected_at": collected,
    }