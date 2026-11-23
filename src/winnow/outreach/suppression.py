"""Suppression list: refuse re-contact."""

from __future__ import annotations

from pathlib import Path


class SuppressionStore:
    """In-memory suppression with optional append-only file backing (tests)."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._contacted: set[str] = set()
        if path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    self._contacted.add(line)

    def is_suppressed(self, candidate_id: str) -> bool:
        return candidate_id in self._contacted

    def mark_contacted(self, candidate_id: str) -> None:
        if candidate_id in self._contacted:
            return
        self._contacted.add(candidate_id)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(f"{candidate_id}\n")

    def clear(self) -> None:
        self._contacted.clear()