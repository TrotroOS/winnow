from __future__ import annotations

from winnow.sources.adapter import SourceAdapter

_adapters: dict[str, SourceAdapter] = {}


def register(adapter: SourceAdapter) -> None:
    """Register a source adapter by its ``name``."""
    _adapters[adapter.name] = adapter


def get(name: str) -> SourceAdapter:
    """Return the adapter registered under ``name``."""
    try:
        return _adapters[name]
    except KeyError as exc:
        raise KeyError(f"unknown source adapter: {name!r}") from exc


def list_adapters() -> list[SourceAdapter]:
    """Return all registered adapters (unordered)."""
    return list(_adapters.values())


def clear() -> None:
    """Remove all registrations (for tests)."""
    _adapters.clear()