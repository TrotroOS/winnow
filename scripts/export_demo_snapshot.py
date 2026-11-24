#!/usr/bin/env python3
"""Export mock demo pipeline output to public/demo-snapshot.json for the Node web app."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from demo import _module_table, execute_demo  # noqa: E402
from winnow.models import Candidate  # noqa: E402


def _candidate_dict(c: Candidate) -> dict[str, object]:
    return {
        "id": c.id,
        "name": c.name,
        "org": c.org,
        "role": c.role,
        "signals": dict(c.signals),
        "contacts": dict(c.contacts),
        "source": c.source,
        "collected_at": c.collected_at.isoformat(),
    }


def _module_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in _module_table().strip().splitlines()[3:]:
        if " | " not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 4:
            rows.append(
                {
                    "module": parts[0],
                    "implemented": parts[1],
                    "tested": parts[2],
                    "notes": parts[3],
                }
            )
    return rows


def build_snapshot(data: dict[str, object]) -> dict[str, object]:
    situation = data["situation"]
    criteria = data["criteria"]
    invariants = data["invariants"]

    return {
        "template_name": data["template_name"],
        "situation": {
            "stage": situation.stage,
            "product": situation.product,
            "goal": situation.goal,
            "constraint": situation.constraint,
            "segment": situation.segment,
            "channels": list(situation.channels),
        },
        "criteria_names": [c.name for c in criteria],  # type: ignore[union-attr]
        "filter_now": data["filter_now"].isoformat(),  # type: ignore[union-attr]
        "possible": [_candidate_dict(c) for c in data["possible"]],  # type: ignore[union-attr]
        "noise_dropped": data["noise_dropped"],
        "dedupe_dropped": data["dedupe_dropped"],
        "by_predicate": data["by_predicate"],
        "intent_lines": data["intent_lines"],
        "preview": data["preview"],
        "invariants": [
            {"name": name, "ok": ok, "detail": detail}
            for name, ok, detail in invariants  # type: ignore[union-attr]
        ],
        "modules": _module_rows(),
        "fail_lines": data["fail_lines"],
    }


def main() -> int:
    data = execute_demo()
    snapshot = build_snapshot(data)
    out_dir = _REPO_ROOT / "public"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "demo-snapshot.json"
    out_path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out_path}")
    if snapshot["fail_lines"]:
        print("Warning: demo invariants failed:", snapshot["fail_lines"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())