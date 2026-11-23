"""JSON bridge for external callers (Forge HTTP remote). BINARY ONLY — no scores."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from winnow.audit import build_audit_entry
from winnow.criteria_builder import build_criteria
from winnow.orchestrator import run_winnow
from winnow.situation_parser import parse_situation

from winnow.adapters.fixture import FixtureSourceAdapter

_DEMO_RECORDS: list[dict[str, Any]] = [
    {
        "id": "demo-1",
        "name": "Avery Chen",
        "org": "Northwind Labs",
        "role": "Head of Product",
        "contacts": {"email": "avery@northwind.test"},
        "collected_at": datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc).isoformat(),
    },
    {
        "id": "demo-2",
        "name": "Blake",
        "org": "",
        "role": "Engineer",
        "contacts": {"email": "blake@example.test"},
        "collected_at": datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc).isoformat(),
    },
]


def describe_situation_payload(situation: str) -> dict[str, Any]:
    """Situation parse + criteria names only (no run)."""
    situation_type = parse_situation(situation)
    criteria_names = [c.name for c in build_criteria(situation_type)]
    return {
        "binary_only": True,
        "situation_input": situation,
        "situation_type": situation_type,
        "criteria_names": criteria_names,
        "note": "Candidates are POSSIBLE or NOISE only. No scores or rankings.",
    }


def demo_adapters() -> list[FixtureSourceAdapter]:
    return [FixtureSourceAdapter("fixture_primary", _DEMO_RECORDS, cost_rank=0)]


def run_for_http(situation: str) -> dict[str, Any]:
    """Run the Python pipeline and return an audit-oriented JSON dict."""
    result = run_winnow(situation, demo_adapters())
    entry = build_audit_entry(result)
    return {
        "binary_only": True,
        "situation_type": entry["situation_type"],
        "criteria_names": entry["criteria_names"],
        "sources": entry["sources"],
        "possible_count": entry["possible_count"],
        "noise_dropped": entry["noise_dropped"],
        "outreach": entry["outreach"],
        "audit_summary": {
            "timestamp": entry["timestamp"],
            "possible_refs": entry["possible_refs"],
        },
    }