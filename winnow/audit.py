"""Audit log writer for each run."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from winnow.models import OutreachCounts, RunResult


def _candidate_ref(c: Any) -> dict[str, str]:
    return {"id": c.id, "name": c.name, "org": c.org, "source": c.source}


def build_audit_entry(result: RunResult) -> dict[str, Any]:
    """Structured audit payload: situation -> criteria -> sources -> counts."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "situation_type": result.situation_type,
        "criteria_names": list(result.criteria_names),
        "sources": list(result.sources),
        "possible_count": len(result.possible),
        "possible_refs": [_candidate_ref(c) for c in result.possible],
        "noise_dropped": result.noise_dropped,
        "outreach": asdict(result.outreach),
    }


def write_audit_log(result: RunResult, path: Path | str) -> None:
    """Append one JSON line audit record."""
    entry = build_audit_entry(result)
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, separators=(",", ":")) + "\n")