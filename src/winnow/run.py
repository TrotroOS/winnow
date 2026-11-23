"""CLI entry: safe, repeatable pipeline runs from YAML config."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from winnow.budget import SpendTracker
from winnow.store import WinnowStore, db_path
from winnow.feedback import TemplateStats, emit_suggestions, suggest
from winnow.criteria.builder import build_criteria, parse_situation
from winnow.models import Candidate, RunResult
from winnow.orchestrator import RunConfig, run
from winnow.outreach.batch_send import SendBatchConfig, send_batch
from winnow.outreach.guards import resolve_manual_approve
from winnow.outreach.engine import NoopTransport
from winnow.outreach.sender import OutreachSender
from winnow.outreach.suppression import SuppressionStore
from winnow.outreach.throttle import Throttle
from winnow.outreach.tracker import OutreachTracker
from winnow.outreach.warmup import effective_daily_cap
from winnow.sources.csv_fixture import CsvFixtureSource
from winnow.sources.mock import MockSource
from winnow.sources.registry import clear, register


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError as exc:
        msg = "PyYAML required; install with: pip install 'winnow[cli]'"
        raise SystemExit(msg) from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"config root must be a mapping: {path}")
    return data


def _situation_from_config(raw: dict) -> dict:
    situation = raw.get("situation")
    if isinstance(situation, dict):
        return dict(situation)
    return {
        "stage": raw.get("stage", "seed"),
        "product": raw.get("product", ""),
        "goal": raw.get("goal", ""),
        "constraint": raw.get("constraint", ""),
        "segment": raw.get("segment", "devtools"),
        "channels": (raw.get("channel", "email"),),
        "situation_type": raw.get("situation_type", "community"),
    }


def _adapter_for(name: str):
    if name == "mock":
        return MockSource()
    if name == "csv_fixture":
        return CsvFixtureSource()
    raise SystemExit(f"unsupported source {name!r}")


def _source_names_from_config(raw: dict) -> list[str]:
    sources = raw.get("sources")
    if isinstance(sources, (list, tuple)):
        return [str(s) for s in sources]
    if raw.get("source"):
        return [str(raw["source"])]
    return ["mock"]


def register_sources_from_config(raw: dict) -> None:
    """Register every adapter listed in config (order preserved before router sort)."""
    clear()
    for name in _source_names_from_config(raw):
        register(_adapter_for(name))


def _run_config_from_yaml(
    raw: dict,
    *,
    limit: int | None,
    dry_run: bool,
    spend_log_path: Path,
    audit_log_path: Path,
    manual_approve: bool,
) -> RunConfig:
    daily_cap = effective_daily_cap(
        ceiling=int(raw.get("daily_cap", 25)),
        warmup_start_daily_cap=int(raw.get("warmup_start_daily_cap", 5)),
        warmup_step=int(raw.get("warmup_step", 5)),
        warmup_start_date=raw.get("warmup_start_date"),
    )
    search_limit = int(limit if limit is not None else raw.get("search_limit", 50))
    max_sends = int(
        raw.get(
            "max_sends_per_run",
            raw.get("per_run_send_cap", 25),
        )
    )
    return RunConfig(
        max_spend_per_run=float(raw.get("max_spend_per_run", 5)),
        max_spend_per_month=float(raw.get("max_spend_per_month", 100)),
        audit_log_path=audit_log_path,
        spend_log_path=spend_log_path,
        search_limit=search_limit,
        manual_approve=manual_approve,
        dry_run=dry_run,
        daily_cap=daily_cap,
        max_sends_per_run=max_sends,
    )


def _batch_path(logs_dir: Path, ts: datetime) -> Path:
    stamp = ts.strftime("%Y%m%dT%H%M%SZ")
    return logs_dir / f"batch_{stamp}.json"


def write_manual_batch_file(
    *,
    path: Path,
    situation_type: str,
    possible: tuple[Candidate, ...],
    criteria: list,
    daily_cap: int,
    transport: object | None = None,
) -> Path:
    """Stage outreach messages to JSON; never sends via transport."""
    caps = {"email": daily_cap, "linkedin": daily_cap, "dm": daily_cap}
    sender = OutreachSender(
        transport=transport or NoopTransport(),
        suppression=SuppressionStore(),
        throttle=Throttle(caps=caps),
        tracker=OutreachTracker(),
    )
    batch = sender.build_batch(
        situation_type=situation_type,
        possible=possible,
        criteria=criteria,
        manual_approve=True,
    )
    payload = {
        "batch_id": batch.batch_id,
        "situation_type": situation_type,
        "message_count": len(batch.messages),
        "messages": [asdict(m) for m in batch.messages],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def format_run_summary(
    *,
    situation: dict,
    result: RunResult,
    month_spent: float,
    month_cap: float,
    batch_path: Path | None,
    sources_used: tuple[str, ...],
) -> str:
    lines = [
        f"situation: {situation}",
        f"template: {result.situation_type}",
        f"criteria_names: {list(result.criteria_names)}",
        f"sources_used: {list(sources_used)}",
        f"possible: {len(result.possible)}",
        f"noise_dropped: {result.noise_dropped}",
        f"enriched: {result.enriched_count}",
        f"backlog: {result.backlog_count}",
        f"spend_this_run: ${result.spend_this_run:.2f}",
        f"monthly_spend: ${month_spent:.2f} / ${month_cap:.2f}",
        f"batch_path: {batch_path or '(none)'}",
    ]
    return "\n".join(lines)


def execute(
    config_path: Path,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    logs_dir: Path | None = None,
) -> tuple[RunResult, str]:
    raw = _load_yaml(config_path)
    situation_input = _situation_from_config(raw)
    register_sources_from_config(raw)

    base_logs = logs_dir or Path("logs")
    spend_log = base_logs / "spend.json"
    audit_log = base_logs / "runs.jsonl"
    sqlite_path = db_path() if logs_dir is None else (base_logs / "winnow.sqlite")
    store = WinnowStore(sqlite_path)
    store.migrate_legacy(
        spend_json=spend_log,
        suppression_files=(base_logs / "suppression.txt",),
    )
    outreach_mode = str(raw.get("outreach_mode", "manual_approve"))
    manual_approve, guard_warning = resolve_manual_approve(
        outreach_mode,
        audit_log_path=audit_log,
    )
    if guard_warning:
        print(guard_warning, file=sys.stderr)
    run_cfg = _run_config_from_yaml(
        raw,
        limit=limit,
        dry_run=dry_run,
        spend_log_path=spend_log,
        audit_log_path=audit_log,
        manual_approve=manual_approve,
    )
    run_cfg.store = store

    result = run(situation_input, run_cfg)

    situation = parse_situation(situation_input)
    criteria, _, template = build_criteria(situation)

    batch_path: Path | None = None
    if run_cfg.manual_approve and result.possible:
        ts = datetime.now(timezone.utc)
        batch_path = _batch_path(base_logs, ts)
        write_manual_batch_file(
            path=batch_path,
            situation_type=template,
            possible=result.possible,
            criteria=criteria,
            daily_cap=run_cfg.daily_cap,
        )

    month_tracker = SpendTracker(
        run_cfg.max_spend_per_run,
        run_cfg.max_spend_per_month,
        store=store,
    )
    summary = format_run_summary(
        situation=situation_input,
        result=result,
        month_spent=month_tracker.month_spent,
        month_cap=run_cfg.max_spend_per_month,
        batch_path=batch_path,
        sources_used=result.sources,
    )

    feedback = suggest(
        template,
        TemplateStats(0, 0),
        possible_count=len(result.possible),
        daily_cap=run_cfg.daily_cap,
        predicate_names=tuple(c.name for c in criteria),
        matched_signal_hint=criteria[0].name if criteria else "matched_signal",
    )
    if "exceeds" in feedback or "below operator bound" in feedback:
        emit_suggestions(
            feedback,
            log_path=base_logs / "feedback.jsonl",
            template_name=template,
        )

    return result, summary


def _send_batch_config_from_yaml(raw: dict) -> SendBatchConfig:
    return SendBatchConfig(
        daily_cap=effective_daily_cap(
            ceiling=int(raw.get("daily_cap", 25)),
            warmup_start_daily_cap=int(raw.get("warmup_start_daily_cap", 5)),
            warmup_step=int(raw.get("warmup_step", 5)),
            warmup_start_date=raw.get("warmup_start_date"),
        ),
        per_run_send_cap=int(raw.get("per_run_send_cap", raw.get("daily_cap", 25))),
        warmup_start_daily_cap=int(raw.get("warmup_start_daily_cap", 5)),
        warmup_step=int(raw.get("warmup_step", 5)),
        warmup_start_date=raw.get("warmup_start_date"),
        from_address=str(raw.get("email_from", "outreach@example.com")),
        unsubscribe_url=str(raw.get("unsubscribe_url", "https://example.com/unsubscribe")),
    )


def cmd_send_batch(args: argparse.Namespace) -> int:
    config_path = args.config
    raw: dict = {}
    if config_path and config_path.is_file():
        raw = _load_yaml(config_path)
    elif config_path and not config_path.is_file():
        print(f"config not found: {config_path}", file=sys.stderr)
        return 1

    if not args.batch_path.is_file():
        print(f"batch not found: {args.batch_path}", file=sys.stderr)
        return 1

    summary = send_batch(
        args.batch_path,
        confirm=args.confirm,
        config=_send_batch_config_from_yaml(raw),
    )
    print(
        f"sent={summary.sent} skipped={summary.skipped} "
        f"suppressed={summary.suppressed} bounced={summary.bounced}"
    )
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    from winnow.scheduler import scheduled_job, run_scheduler_loop

    if not args.config.is_file():
        print(f"config not found: {args.config}", file=sys.stderr)
        return 1
    if args.once:
        code, _ = scheduled_job(args.config, logs_dir=args.logs_dir)
        return code
    try:
        run_scheduler_loop(args.config, logs_dir=args.logs_dir)
    except KeyboardInterrupt:
        return 0
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if not args.config.is_file():
        print(f"config not found: {args.config}", file=sys.stderr)
        return 1
    _, summary = execute(args.config, limit=args.limit, dry_run=args.dry_run)
    print(summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    if argv and argv[0] not in {"run", "send-batch", "schedule"}:
        argv = ["run", *argv]

    parser = argparse.ArgumentParser(description="Winnow CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run pipeline from YAML config")
    run_parser.add_argument("--config", type=Path, required=True)
    run_parser.add_argument("--limit", type=int, default=None)
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.set_defaults(_handler=cmd_run)

    send_parser = sub.add_parser("send-batch", help="Deliver a staged outreach batch")
    send_parser.add_argument("batch_path", type=Path)
    send_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required to perform sends; without it nothing is delivered",
    )
    send_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Config for caps and email settings (no secrets in file)",
    )
    send_parser.set_defaults(_handler=cmd_send_batch)

    sched_parser = sub.add_parser(
        "schedule",
        help="Daily dry-run + manual batch (never auto-sends)",
    )
    sched_parser.add_argument("--config", type=Path, required=True)
    sched_parser.add_argument(
        "--once",
        action="store_true",
        help="Run one scheduler cycle immediately",
    )
    sched_parser.add_argument("--logs-dir", type=Path, default=None)
    sched_parser.set_defaults(_handler=cmd_schedule)

    args = parser.parse_args(argv)
    return args._handler(args)


if __name__ == "__main__":
    raise SystemExit(main())