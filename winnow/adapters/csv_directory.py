"""Read candidate records from CSV files in a local directory."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from winnow.adapters.base import SourceAdapter


class CsvDirectorySourceAdapter(SourceAdapter):
    """Loads all ``*.csv`` files from a directory (local, no paid API)."""

    def __init__(self, directory: str | Path, *, cost_rank: int = 1) -> None:
        self._directory = Path(directory)
        self._cost_rank = cost_rank

    @property
    def name(self) -> str:
        return f"csv:{self._directory}"

    @property
    def cost_rank(self) -> int:
        return self._cost_rank

    def fetch_raw(self) -> list[dict[str, Any]]:
        if not self._directory.is_dir():
            return []

        records: list[dict[str, Any]] = []
        for path in sorted(self._directory.glob("*.csv")):
            records.extend(self._read_csv(path))
        return records

    def _read_csv(self, path: Path) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if not row:
                    continue
                record = {k.strip(): (v or "").strip() for k, v in row.items() if k}
                if record.get("signals") and isinstance(record["signals"], str):
                    # leave as string; normalize stage can parse JSON later if needed
                    pass
                record.setdefault("id", record.get("id") or f"{path.stem}-{len(out)}")
                out.append(record)
        return out