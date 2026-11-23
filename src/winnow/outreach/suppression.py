"""Suppression list: refuse re-contact."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from winnow.store import WinnowStore


class SuppressionStore:
    """In-memory, file-backed (tests), or SQLite store-backed suppression."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        store: WinnowStore | None = None,
    ) -> None:
        self._path = path
        self._store = store
        self._contacted: set[str] = set()
        if store is not None:
            self._contacted.update(store.suppression_ids())
        elif path and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    self._contacted.add(line)

    def is_suppressed(self, candidate_id: str) -> bool:
        if self._store is not None:
            return candidate_id in self._store.suppression_ids()
        return candidate_id in self._contacted

    def mark_contacted(self, candidate_id: str) -> None:
        if self._store is not None:
            try:
                self._store.set_candidate_status(candidate_id, "contacted")
            except ValueError:
                pass
            return
        if candidate_id in self._contacted:
            return
        self._contacted.add(candidate_id)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(f"{candidate_id}\n")

    def clear(self) -> None:
        self._contacted.clear()