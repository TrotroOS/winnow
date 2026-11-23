"""Parse startup situation into a structured situation type (stub)."""

from __future__ import annotations

from typing import Any


def parse_situation(raw: str | dict[str, Any]) -> str:
    """Return a situation type string. Stub: echoes or defaults."""
    if isinstance(raw, dict):
        return str(raw.get("type", "unknown"))
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return "unknown"