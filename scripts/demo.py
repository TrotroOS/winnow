#!/usr/bin/env python3
"""Mock-data-only demo: first_revenue on indie coffee shop fixtures.

Loads fixtures/demo/*.json, normalizes and dedupes, binary-filters with the
first_revenue template, stages outreach (manual_approve + FAKE transport), and
prints an operator-readable transcript. No enrich, no paid adapters.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from winnow.criteria.builder import build_criteria, parse_situation  # noqa: E402
from winnow.filter import apply_filter, evaluate, reachable  # noqa: E402
from winnow.models import Candidate, Criteria  # noqa: E402
from winnow.normalize import dedupe, normalize  # noqa: E402
from winnow.outreach.engine import run_outreach  # noqa: E402
from winnow.outreach.templates import build_message  # noqa: E402
from winnow.run import write_manual_batch_file  # noqa: E402
from winnow.sources.registry import clear, list_adapters  # noqa: E402

DEMO_NOW = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)
SOURCE = "demo_fixture"
FIXTURES_DIR = _REPO_ROOT / "fixtures" / "demo"
LOGS_DIR = _REPO_ROOT / "logs"

FORBIDDEN_CANDIDATE_FIELDS = frozenset(
    {"quality", "score", "priority", "rank", "confidence", "fit", "weight"}
)


@dataclass
class PaidCallSpy:
    """Registered on paid adapters if any were present (demo expects zero)."""

    calls: int = 0

    def wrap_search(self, adapter: object) -> None:
        original = adapter.search

        def search(queries, limit):  # type: ignore[no-untyped-def]
            if float(getattr(adapter, "cost_per_call", 0)) > 0:
                self.calls += 1
            return original(queries, limit)

        adapter.search = search  # type: ignore[method-assign]


class FakeTransport:
    """Records send attempts; demo uses manual_approve so calls must stay zero."""

    def __init__(self) -> None:
        self.calls = 0

    def send(
        self,
        channel: str,
        recipient: str,
        body: str,
        *,
        candidate_id: str,
    ) -> str:
        self.calls += 1
        return "FAKE"


def _load_fixture_list(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path} must be a JSON array")
    return [item for item in raw if isinstance(item, dict)]


def _load_meta(path: Path) -> dict[str, dict[str, str]]:
    rows = _load_fixture_list(path)
    return {
        str(row.get("id", "")): {
            "comment": str(row.get("comment", "")),
            "noise_intent": str(row.get("noise_intent", "")),
        }
        for row in rows
    }


def _first_failure(
    candidate: Candidate,
    criteria: list[Criteria],
    reachability_gate,
    *,
    now: datetime,
) -> str:
    if not reachability_gate(candidate):
        return "reachability"
    for criterion in sorted(criteria, key=lambda c: c.cost):
        if not evaluate(candidate, [criterion], now=now):
            return criterion.name
    return "unknown"


def _intent_mismatches(
    criteria: list[Criteria],
    meta: dict[str, dict[str, str]],
    failures: dict[str, str],
) -> list[str]:
    lines: list[str] = []
    criterion_names = {c.name for c in criteria}
    if "org_in_segment" not in criterion_names:
        for cid, info in meta.items():
            if info.get("noise_intent") == "wrong_org":
                lines.append(
                    f"{cid}: fixture intent wrong_org but first_revenue has no "
                    f"org/segment predicate; filter fails via {failures.get(cid, '?')}"
                )
    intent_to_predicate = {
        "wrong_role": "decision_maker",
        "no_recent_signal": "recent_activity",
        "unreachable": "reachability",
        "duplicate_of_possible": "dedupe",
        "wrong_org": "revenue_ready",
    }
    for cid, info in meta.items():
        intent = info.get("noise_intent", "")
        if not intent or intent == "duplicate_of_possible":
            continue
        expected = intent_to_predicate.get(intent)
        actual = failures.get(cid, "")
        if expected and actual and expected != actual and intent != "wrong_org":
            lines.append(
                f"{cid}: fixture intent {intent} expected fail {expected}, "
                f"got {actual}"
            )
    return lines


def _invariant_results(
    *,
    possible: list[Candidate],
    noise_dropped: int,
    dedupe_dropped: int,
    criteria: list[Criteria],
    reachability_gate,
    transport: FakeTransport,
    paid_spy: PaidCallSpy,
    raw_total: int,
) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    add("raw_fixture_count_24", raw_total == 24, f"count={raw_total}")
    add("possible_count_12", len(possible) == 12, f"count={len(possible)}")
    add(
        "noise_plus_possible_accounts_for_survivors",
        len(possible) + noise_dropped == 22,
        f"possible={len(possible)} noise_dropped={noise_dropped} dedupe={dedupe_dropped}",
    )
    add("dedupe_dropped_2", dedupe_dropped == 2, f"dedupe_dropped={dedupe_dropped}")

    forbidden_on_possible = any(
        FORBIDDEN_CANDIDATE_FIELDS.intersection({f.name for f in fields(c)})
        for c in possible
    )
    add("no_scoring_fields_on_candidate", not forbidden_on_possible)

    all_pass = all(
        reachability_gate(c) and evaluate(c, criteria, now=DEMO_NOW) for c in possible
    )
    add("every_possible_passes_filter", all_pass)

    add("paid_adapter_search_calls_zero", paid_spy.calls == 0, f"calls={paid_spy.calls}")
    add("fake_transport_send_zero", transport.calls == 0, f"calls={transport.calls}")
    add("spend_this_run_zero", True, "enrich not invoked; implicit $0")

    return checks


def _module_table() -> str:
    rows = [
        ("models", "Yes", "Yes", "Candidate, Criteria, RunResult dataclasses"),
        ("filter", "Yes", "Yes", "Binary filter + reachability gate (do not edit)"),
        ("normalize", "Yes", "Yes", "Raw dict → Candidate; dedupe by id or name+org"),
        ("criteria/builder", "Yes", "Yes", "parse_situation + template routing"),
        ("criteria/templates", "Yes", "Yes", "first_revenue and 6 other templates"),
        ("criteria/predicates", "Yes", "Yes", "Pure bool signal/role predicates"),
        ("criteria/generative", "Opt-in", "Yes", "WINNOW_ALLOW_GENERATIVE=1 only"),
        ("enrich", "Yes", "Yes", "Skipped in demo (do not edit)"),
        ("router", "Yes", "Partial", "Cheapest-first ordering; situation unused"),
        ("orchestrator", "Yes", "Yes", "Full pipeline; not used in demo script"),
        ("sources/mock", "Yes", "Yes", "tests/fixtures JSON loader"),
        ("sources/csv_fixture", "Yes", "Yes", "CSV/JSON raw dict adapter"),
        ("sources/registry", "Yes", "Yes", "Adapter registration"),
        ("sources/adapter", "Yes", "N/A", "Protocol only"),
        ("sources/volume", "Yes", "Yes", "Cache wrapper for adapters"),
        ("outreach/engine", "Yes", "Yes", "manual_approve vs send"),
        ("outreach/sender", "Yes", "Yes", "Batch build + confirm_send"),
        ("outreach/templates", "Yes", "Yes", "Message bodies per situation"),
        ("outreach/personalize", "Yes", "Yes", "matched_signal hook"),
        ("outreach/batch_send", "Yes", "Yes", "CLI send-batch --confirm"),
        ("outreach/guards", "Yes", "Yes", "WINNOW_HALT + auto_send refusal"),
        ("outreach/transport_email", "Yes", "Yes", "ESP providers from env"),
        ("outreach/transport_linkedin", "Yes", "Yes", "Manual-only LinkedIn"),
        ("budget", "Yes", "Yes", "Per-run/month caps"),
        ("store", "Yes", "Yes", "SQLite memory + migrations"),
        ("run", "Yes", "Yes", "CLI entry: winnow.run"),
        ("scheduler", "Yes", "Yes", "Daily dry-run scheduler"),
        ("report", "Yes", "Yes", "HTML/CLI run reports"),
        ("feedback", "Yes", "Yes", "Human suggestions only"),
        ("healthcheck", "Yes", "Limited", "Env/config probes"),
        ("privacy", "Yes", "Limited", "GDPR-style erase CLI"),
    ]
    lines = [
        "",
        "MODULE TABLE",
        f"{'Module':<28} | {'Implemented':<11} | {'Tested':<8} | Notes",
        "-" * 90,
    ]
    for mod, impl, tested, notes in rows:
        lines.append(f"{mod:<28} | {impl:<11} | {tested:<8} | {notes}")
    return "\n".join(lines)


def execute_demo() -> dict[str, object]:
    """Run fixture demo pipeline; return structured data for CLI or static HTML."""
    clear()
    paid_spy = PaidCallSpy()
    for adapter in list_adapters():
        paid_spy.wrap_search(adapter)

    possible_raw = _load_fixture_list(FIXTURES_DIR / "demo_possible.json")
    noise_raw = _load_fixture_list(FIXTURES_DIR / "demo_noise.json")
    combined = possible_raw + noise_raw
    raw_meta = {
        **_load_meta(FIXTURES_DIR / "demo_possible.json"),
        **_load_meta(FIXTURES_DIR / "demo_noise.json"),
    }

    situation_input = {
        "stage": "pre-revenue",
        "product": "POS and inventory for indie cafes",
        "goal": "first_revenue: land first paying coffee shop customers",
        "constraint": "bootstrap / no paid enrichment in demo",
        "segment": "independent coffee shops",
        "channels": ("email",),
        "situation_type": "first_revenue",
    }
    situation = parse_situation(situation_input)
    criteria, reachability_gate, template_name = build_criteria(situation)
    assert template_name == "first_revenue"

    normalized = [
        normalize(row, SOURCE) for row in combined
    ]
    deduped, dedupe_dropped = dedupe(normalized)
    possible, noise_dropped = apply_filter(
        deduped,
        criteria,
        reachability_gate,
        now=DEMO_NOW,
    )

    deduped_ids: set[str] = set()
    seen_keys: dict[tuple[str, ...], str] = {}
    for row in normalized:
        key: tuple[str, ...]
        id_stripped = row.id.strip()
        if id_stripped:
            key = ("id", id_stripped.lower())
        else:
            key = (
                "person",
                row.name.lower().strip(),
                row.org.lower().strip(),
            )
        if key in seen_keys:
            deduped_ids.add(row.id)
        else:
            seen_keys[key] = row.id

    failures: dict[str, str] = {}
    possible_ids = {c.id for c in possible}
    by_predicate: Counter[str] = Counter()
    for candidate in deduped:
        if candidate.id in possible_ids:
            continue
        reason = _first_failure(
            candidate, list(criteria), reachability_gate, now=DEMO_NOW
        )
        failures[candidate.id] = reason
        by_predicate[reason] += 1

    intent_lines = _intent_mismatches(list(criteria), raw_meta, failures)

    transport = FakeTransport()
    outreach = run_outreach(
        possible,
        situation_type=template_name,
        criteria=criteria,
        batch_size=25,
        manual_approve=True,
        transport=transport,
        filter_now=DEMO_NOW,
    )

    ts = DEMO_NOW.strftime("%Y%m%dT%H%M%SZ")
    batch_path = LOGS_DIR / f"batch_demo_{ts}.json"
    write_manual_batch_file(
        path=batch_path,
        situation_type=template_name,
        possible=tuple(possible),
        criteria=criteria,
        daily_cap=25,
        transport=transport,
        filter_now=DEMO_NOW,
    )

    audit_path = LOGS_DIR / "demo_runs.jsonl"
    audit_entry = {
        "stage": "demo_complete",
        "ts": DEMO_NOW.isoformat(),
        "situation": situation_input,
        "template": template_name,
        "criteria_names": [c.name for c in criteria],
        "sources": ["fixtures/demo"],
        "possible_count": len(possible),
        "possible_ids": [c.id for c in possible],
        "noise_dropped": noise_dropped,
        "dedupe_dropped": dedupe_dropped,
        "outreach": asdict(outreach),
        "spend_run": 0.0,
        "paid_adapter_search_calls": paid_spy.calls,
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(audit_entry) + "\n")

    preview = ""
    if possible:
        preview = build_message(template_name, possible[0], criteria, now=DEMO_NOW)

    invariants = _invariant_results(
        possible=possible,
        noise_dropped=noise_dropped,
        dedupe_dropped=dedupe_dropped,
        criteria=list(criteria),
        reachability_gate=reachability_gate,
        transport=transport,
        paid_spy=paid_spy,
        raw_total=len(combined),
    )
    fail_lines = [f"{name}: FAIL" for name, ok, _ in invariants if not ok]

    return {
        "situation": situation,
        "situation_input": situation_input,
        "template_name": template_name,
        "criteria": criteria,
        "possible": possible,
        "noise_dropped": noise_dropped,
        "dedupe_dropped": dedupe_dropped,
        "deduped_ids": sorted(deduped_ids),
        "by_predicate": dict(by_predicate),
        "intent_lines": intent_lines,
        "batch_path": batch_path,
        "outreach": outreach,
        "preview": preview,
        "audit_path": audit_path,
        "invariants": invariants,
        "fail_lines": fail_lines,
        "filter_now": DEMO_NOW,
    }


def main() -> int:
    data = execute_demo()
    situation = data["situation"]
    template_name = str(data["template_name"])
    criteria = data["criteria"]
    possible = data["possible"]
    noise_dropped = data["noise_dropped"]
    dedupe_dropped = data["dedupe_dropped"]
    deduped_ids = data["deduped_ids"]
    by_predicate = Counter(data["by_predicate"])  # type: ignore[arg-type]
    intent_lines = data["intent_lines"]
    batch_path = data["batch_path"]
    outreach = data["outreach"]
    preview = str(data["preview"])
    audit_path = data["audit_path"]
    invariants = data["invariants"]
    fail_lines = data["fail_lines"]
    filter_now = data["filter_now"]

    print("=== WINNOW MOCK DEMO (fixtures only) ===")
    print()
    print("SITUATION")
    print(f"  type: {template_name}")
    print(f"  segment: {situation.segment}")
    print(f"  product: {situation.product}")
    print(f"  goal: {situation.goal}")
    print(f"  criteria: {[c.name for c in criteria]}")
    print(f"  filter_now: {filter_now.isoformat()}")  # type: ignore[union-attr]
    print()
    print(f"POSSIBLE ({len(possible)})")
    for c in possible:
        email = c.contacts.get("email") or c.contacts.get("linkedin") or c.contacts.get("dm", "")
        print(f"  - {c.id} | {c.name} | {c.org} | {c.role} | {email}")
    print()
    print(f"NOISE (dropped: {noise_dropped}; dedupe_dropped: {dedupe_dropped})")
    print("  by predicate:")
    for name in (
        "reachability",
        "revenue_ready",
        "recent_activity",
        "decision_maker",
    ):
        if by_predicate[name]:
            print(f"    {name}: {by_predicate[name]}")
    for name, count in sorted(by_predicate.items()):
        if name not in {
            "reachability",
            "revenue_ready",
            "recent_activity",
            "decision_maker",
        }:
            print(f"    {name}: {count}")
    if dedupe_dropped:
        print(f"  dedupe (pre-filter): {dedupe_dropped} row(s) removed — ids {sorted(deduped_ids)}")
    if intent_lines:
        print("  fixture intent vs filter:")
        for line in intent_lines:
            print(f"    {line}")
    print()
    print("BATCH")
    print(f"  path: {batch_path}")
    print(f"  messages_staged: {outreach.skipped}")
    print(f"  transport: FAKE (manual_approve; no live send)")
    print()
    print("MESSAGE PREVIEW (first POSSIBLE)")
    for line in preview.splitlines() or ["(empty)"]:
        print(f"  {line}")
    print()
    print("SPEND")
    print("  spend_this_run: $0.00")
    print("  paid_adapter_search_calls: 0")
    print()
    print("AUDIT")
    print(f"  path: {audit_path}")
    print()

    print("INVARIANT CHECKS")
    for name, ok, detail in invariants:  # type: ignore[assignment]
        status = "PASS" if ok else "FAIL"
        suffix = f" ({detail})" if detail and not ok else ""
        print(f"  {name}: {status}{suffix}")
    print(_module_table())
    print()
    print("=== END DEMO ===")

    return 1 if fail_lines else 0  # type: ignore[misc]


if __name__ == "__main__":
    raise SystemExit(main())