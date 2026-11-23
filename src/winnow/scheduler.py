"""Daily scheduled dry-run + manual batch staging (never auto-sends)."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
from datetime import date, datetime, time as dt_time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from winnow.budget import SpendTracker
from winnow.criteria.builder import build_criteria, parse_situation
from winnow.feedback import (
    LIST_SIZE_DAILY_CAP_MULTIPLIER,
    POSSIBLE_COUNT_TOO_SMALL,
    TemplateStats,
    suggest,
)
from winnow.orchestrator import RunConfig, run
from winnow.outreach.guards import sends_halted
from winnow.run import (
    _batch_path,
    _load_yaml,
    _run_config_from_yaml,
    _situation_from_config,
    format_run_summary,
    register_sources_from_config,
    write_manual_batch_file,
)
from winnow.store import WinnowStore, db_path

DEFAULT_DAILY_RUN_TIME = "09:00"
DEFAULT_LOCK_PATH = Path("logs/winnow.run.lock")
DEFAULT_STATE_PATH = Path("logs/scheduler.state.json")
DEFAULT_NOTIFICATIONS = Path("logs/notifications.jsonl")
POLL_SECONDS = 60


def parse_daily_run_time(value: str | None) -> dt_time:
    text = (value or DEFAULT_DAILY_RUN_TIME).strip()
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError(f"invalid daily_run_time {value!r}; use HH:MM")
    hour, minute = int(parts[0]), int(parts[1])
    return dt_time(hour, minute)


def config_timezone(raw: dict) -> ZoneInfo:
    key = raw.get("timezone") or raw.get("tz") or "UTC"
    return ZoneInfo(str(key))


def operator_bounds(raw: dict, daily_cap: int) -> tuple[int, int]:
    minimum = int(raw.get("possible_min", POSSIBLE_COUNT_TOO_SMALL))
    default_max = daily_cap * LIST_SIZE_DAILY_CAP_MULTIPLIER
    maximum = int(raw.get("possible_max", default_max))
    return minimum, maximum


def possible_within_bounds(count: int, minimum: int, maximum: int) -> bool:
    return minimum <= count <= maximum


def expected_run_cost(raw: dict) -> float:
    return float(raw.get("max_spend_per_run", 5))


def _load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def local_date(now_utc: datetime, tz: ZoneInfo) -> date:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(tz).date()


def local_time(now_utc: datetime, tz: ZoneInfo) -> dt_time:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(tz).timetz().replace(tzinfo=None)


def should_fire_daily(
    now_utc: datetime,
    *,
    state_path: Path,
    run_time: dt_time,
    tz: ZoneInfo,
) -> bool:
    """True when local clock is at/after run_time and we have not run yet today (tz)."""
    today = local_date(now_utc, tz).isoformat()
    state = _load_state(state_path)
    if state.get("last_run_date") == today:
        return False
    return local_time(now_utc, tz) >= run_time


def record_daily_fire(state_path: Path, now_utc: datetime, tz: ZoneInfo) -> None:
    today = local_date(now_utc, tz).isoformat()
    _save_state(state_path, {"last_run_date": today})


def append_notification(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, default=str) + "\n")


def notify(
    *,
    logs_dir: Path,
    reason: str,
    stats: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }
    if stats:
        payload["stats"] = stats
    line = json.dumps(payload, default=str)
    print(line)
    append_notification(logs_dir / "notifications.jsonl", payload)


class RunLock:
    """Exclusive lock; second acquirer gets ``held=False``."""

    def __init__(self, path: Path = DEFAULT_LOCK_PATH) -> None:
        self.path = path
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        self._fd = None

    def __enter__(self) -> RunLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


def scheduled_job(
    config_path: Path,
    *,
    logs_dir: Path | None = None,
    now: datetime | None = None,
) -> tuple[int, str]:
    """One scheduler cycle: dry-run, optional batch file, notification. Never sends."""
    if sends_halted():
        reason = "WINNOW_HALT is set; scheduler blocked"
        notify(logs_dir=logs_dir or Path("logs"), reason=reason)
        return 0, reason

    lock = RunLock((logs_dir or Path("logs")) / "winnow.run.lock")
    if not lock.acquire():
        reason = "concurrent run blocked by lock"
        notify(logs_dir=logs_dir or Path("logs"), reason=reason)
        return 0, reason

    try:
        raw = _load_yaml(config_path)
        base_logs = logs_dir or Path("logs")
        spend_log = base_logs / "spend.json"
        audit_log = base_logs / "runs.jsonl"
        sqlite_path = db_path() if logs_dir is None else (base_logs / "winnow.sqlite")
        store = WinnowStore(sqlite_path)
        store.migrate_legacy(
            spend_json=spend_log,
            suppression_files=(base_logs / "suppression.txt",),
        )

        situation_input = _situation_from_config(raw)
        register_sources_from_config(raw)

        run_cfg = _run_config_from_yaml(
            raw,
            limit=None,
            dry_run=True,
            spend_log_path=spend_log,
            audit_log_path=audit_log,
            manual_approve=True,
        )
        run_cfg.store = store

        run_cost = expected_run_cost(raw)
        month_tracker = SpendTracker(
            run_cfg.max_spend_per_run,
            run_cfg.max_spend_per_month,
            store=store,
        )
        _, month_left = month_tracker.remaining()
        if month_left < run_cost:
            reason = (
                f"insufficient monthly budget: {month_left:.2f} remaining "
                f"< expected run cost {run_cost:.2f}"
            )
            notify(
                logs_dir=base_logs,
                reason=reason,
                stats={"month_left": month_left, "run_cost": run_cost},
            )
            return 0, reason

        filter_now = now
        if filter_now is not None:
            if filter_now.tzinfo is None:
                filter_now = filter_now.replace(tzinfo=timezone.utc)
            run_cfg.filter_now = filter_now

        result = run(situation_input, run_cfg)

        situation = parse_situation(situation_input)
        criteria, _, template = build_criteria(situation)
        minimum, maximum = operator_bounds(raw, run_cfg.daily_cap)
        count = len(result.possible)
        in_bounds = possible_within_bounds(count, minimum, maximum)

        batch_path: Path | None = None
        if in_bounds and result.possible:
            ts = (filter_now or datetime.now(timezone.utc)).astimezone(timezone.utc)
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
            possible_count=count,
            daily_cap=run_cfg.daily_cap,
            predicate_names=tuple(c.name for c in criteria),
            matched_signal_hint=criteria[0].name if criteria else "matched_signal",
        )

        if not in_bounds:
            reason = (
                f"POSSIBLE count {count} outside bounds [{minimum}, {maximum}]; "
                "batch not written"
            )
        elif batch_path is None:
            reason = "dry-run complete; no POSSIBLE candidates"
        else:
            reason = "dry-run complete; manual batch staged"

        stats = {
            "possible": count,
            "noise_dropped": result.noise_dropped,
            "spend_this_run": result.spend_this_run,
            "batch_path": str(batch_path) if batch_path else None,
            "in_bounds": in_bounds,
            "feedback": feedback,
            "outreach_sent": result.outreach.sent,
        }
        notify(logs_dir=base_logs, reason=reason, stats=stats)
        print(summary)
        return 0, reason
    finally:
        lock.release()


def run_scheduler_loop(
    config_path: Path,
    *,
    logs_dir: Path | None = None,
    poll_seconds: int = POLL_SECONDS,
) -> None:
    """Wait for ``daily_run_time`` each day and run one job (never overlapping days)."""
    raw = _load_yaml(config_path)
    run_time = parse_daily_run_time(raw.get("daily_run_time"))
    tz = config_timezone(raw)
    base_logs = logs_dir or Path("logs")
    state_path = base_logs / "scheduler.state.json"

    while True:
        now = datetime.now(timezone.utc)
        if should_fire_daily(now, state_path=state_path, run_time=run_time, tz=tz):
            scheduled_job(config_path, logs_dir=logs_dir, now=now)
            record_daily_fire(state_path, now, tz)
        time.sleep(poll_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Winnow daily scheduler")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one job immediately (ignore daily_run_time)",
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=None,
        help="Directory for logs, lock, and SQLite (default: logs/)",
    )
    args = parser.parse_args(list(argv or sys.argv[1:]))

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


if __name__ == "__main__":
    raise SystemExit(main())