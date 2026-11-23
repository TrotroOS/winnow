"""CLI entry: safe, repeatable pipeline runs from YAML config."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from winnow.budget import SpendTracker
from winnow.criteria.builder import build_criteria, parse_situation
from winnow.models import Candidate, RunResult
from winnow.orchestrator import RunConfig, run
from winnow.outreach.batch_send import SendBatchConfig, send_batch
from winnow.outreach.engine import NoopTransport
from winnow.outreach.sender import OutreachSender
from winnow.outreach.suppression import SuppressionStore
from winnow.outreach.throttle import Throttle
from winnow.outreach.tracker import OutreachTracker
from winnow.outreach.warmup import effective_daily_cap
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


def _register_source(source_name: str) -> None:
    clear()
    if source_name == "mock":
        register(MockSource())
        return
    raise SystemExit(f"unsupported source {source_name!r} (safe default: mock)")


def _run_config_from_yaml(
    raw: dict,
    *,
    limit: int | None,
    dry_run: bool,
    spend_log_path: Path,
    audit_log_path: Path,
) -> RunConfig:
    outreach_mode = str(raw.get("outreach_mode", "manual_approve")).strip().lower()
    manual = outreach_mode in {"manual_approve", "manual", "approve"}
    daily_cap = effective_daily_cap(
        ceiling=int(raw.get("daily_cap", 25)),
        warmup_start_daily_cap=int(raw.get("warmup_start_daily_cap", 5)),
        warmup_step=int(raw.get("warmup_step", 5)),
        warmup_start_date=raw.get("warmup_start_date"),
    )
    search_limit = int(limit if limit is not None else raw.get("search_limit", 50))
    return RunConfig(
        max_spend_per_run=float(raw.get("max_spend_per_run", 5)),
        max_spend_per_month=float(raw.get("max_spend_per_month", 100)),
        audit_log_path=audit_log_path,
        spend_log_path=spend_log_path,
        search_limit=search_limit,
        manual_approve=manual,
        dry_run=dry_run,
        daily_cap=daily_cap,
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
    source_name = str(raw.get("source", "mock"))
    _register_source(source_name)

    base_logs = logs_dir or Path("logs")
    spend_log = base_logs / "spend.json"
    audit_log = base_logs / "runs.jsonl"
    run_cfg = _run_config_from_yaml(
        raw,
        limit=limit,
        dry_run=dry_run,
        spend_log_path=spend_log,
        audit_log_path=audit_log,
    )

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
        spend_log_path=spend_log,
    )
    summary = format_run_summary(
        situation=situation_input,
        result=result,
        month_spent=month_tracker.month_spent,
        month_cap=run_cfg.max_spend_per_month,
        batch_path=batch_path,
        sources_used=result.sources,
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


def cmd_run(args: argparse.Namespace) -> int:
    if not args.config.is_file():
        print(f"config not found: {args.config}", file=sys.stderr)
        return 1
    _, summary = execute(args.config, limit=args.limit, dry_run=args.dry_run)
    print(summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv[1:])
    if argv and argv[0] not in {"run", "send-batch"}:
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

    args = parser.parse_args(argv)
    return args._handler(args)


if __name__ == "__main__":
    raise SystemExit(main())