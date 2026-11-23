"""GDPR export and erasure for stored candidates."""

from __future__ import annotations

import json
from typing import Any

from winnow.store import WinnowStore


def export_candidate(store: WinnowStore, candidate_id: str) -> dict[str, Any]:
    row = store.get_candidate_row(candidate_id)
    if row is None:
        raise KeyError(f"unknown candidate {candidate_id!r}")
    contacts = json.loads(row["contacts_json"] or "{}")
    signals = json.loads(row["signals_json"] or "{}")
    return {
        "id": row["id"],
        "name": row["name"],
        "org": row["org"],
        "role": row["role"],
        "source": row["source"],
        "status": row["status"],
        "contacts": contacts,
        "signals": signals,
        "last_seen": row["last_seen"],
        "suppression_hash": row.get("suppression_hash"),
    }


def erase_candidate(store: WinnowStore, candidate_id: str) -> None:
    store.erase_candidate_pii(candidate_id)