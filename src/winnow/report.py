"""Operator run reports from SQLite memory (no per-candidate scores)."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from winnow.store import WinnowStore, db_path

DEFAULT_ADAPTER_COST: dict[str, float] = {
    "mock": 0.0,
    "csv_fixture": 0.0,
}

_METRICS_SNAPSHOT: dict[str, Any] = {"lines": ""}
_METRICS_SERVER: HTTPServer | None = None


@dataclass(frozen=True, slots=True)
class RunReport:
    run_id: int
    created_at: str
    situation: dict[str, Any]
    template: str
    criteria_names: tuple[str, ...]
    sources: tuple[tuple[str, int, float], ...]
    possible: int
    noise_dropped: int
    enriched: int
    backlog: int
    spend: float
    sends_by_channel: dict[str, int]
    sent: int
    replied: int
    bounced: int
    bounce_rate: float
    reply_rate: float


def metrics_enabled() -> bool:
    value = os.environ.get("WINNOW_METRICS", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def metrics_port() -> int:
    raw = os.environ.get("WINNOW_METRICS_PORT", "9100").strip()
    try:
        return int(raw)
    except ValueError:
        return 9100


def _source_cost_rows(
    store: WinnowStore,
    *,
    run_key: str,
    sources: list[str],
) -> tuple[tuple[str, int, float], ...]:
    calls_by_adapter = {
        str(row["adapter"]): int(row["calls"])
        for row in store.adapter_calls_by_run_key(run_key)
    }
    names = list(sources) or sorted(calls_by_adapter)
    rows: list[tuple[str, int, float]] = []
    for name in names:
        calls = calls_by_adapter.get(name, 0)
        unit = DEFAULT_ADAPTER_COST.get(name, 0.0)
        rows.append((name, calls, unit * calls))
    for name in sorted(calls_by_adapter):
        if name in names:
            continue
        calls = calls_by_adapter[name]
        unit = DEFAULT_ADAPTER_COST.get(name, 0.0)
        rows.append((name, calls, unit * calls))
    return tuple(rows)


def _rates(sent: int, replied: int, bounced: int) -> tuple[float, float]:
    if sent <= 0:
        return (0.0, 0.0)
    return (bounced / sent, replied / sent)


def load_run_report(store: WinnowStore, run_id: int) -> RunReport:
    row = store.get_run(run_id)
    if row is None:
        raise KeyError(f"unknown run id {run_id}")

    outreach = row.get("outreach") or {}
    sent = int(outreach.get("sent", 0))
    replied = int(outreach.get("replied", 0))
    bounced = int(outreach.get("bounced", 0))

    sends_by_channel: dict[str, int] = {}
    send_rows = store.sends_for_run(run_id)
    if send_rows:
        sent = replied = bounced = 0
        for item in send_rows:
            channel = str(item.get("channel") or "unknown")
            count = int(item.get("n", 0))
            sends_by_channel[channel] = sends_by_channel.get(channel, 0) + count
            status = str(item.get("status") or "sent")
            if status == "replied":
                replied += count
            elif status == "bounced":
                bounced += count
            else:
                sent += count

    bounce_rate, reply_rate = _rates(sent, replied, bounced)
    criteria = row.get("criteria_names") or []
    if isinstance(criteria, str):
        criteria = json.loads(criteria)
    situation = row.get("situation") or {}
    sources = row.get("sources") or []
    if isinstance(sources, str):
        sources = json.loads(sources)

    return RunReport(
        run_id=int(row["id"]),
        created_at=str(row["created_at"]),
        situation=dict(situation),
        template=str(row.get("template_name") or row.get("situation_type", "")),
        criteria_names=tuple(str(x) for x in criteria),
        sources=_source_cost_rows(store, run_key=str(row.get("run_key") or ""), sources=sources),
        possible=int(row.get("possible_count", 0)),
        noise_dropped=int(row.get("noise_dropped", 0)),
        enriched=int(row.get("enriched_count", 0)),
        backlog=int(row.get("backlog_count", 0)),
        spend=float(row.get("spend_run", 0.0)),
        sends_by_channel=sends_by_channel,
        sent=sent,
        replied=replied,
        bounced=bounced,
        bounce_rate=bounce_rate,
        reply_rate=reply_rate,
    )


def format_report_text(report: RunReport) -> str:
    lines = [
        f"run_id: {report.run_id}",
        f"created_at: {report.created_at}",
        f"situation: {report.situation}",
        f"template: {report.template}",
        f"criteria_names: {list(report.criteria_names)}",
        "sources:",
    ]
    for name, calls, cost in report.sources:
        lines.append(f"  {name}: calls={calls} cost=${cost:.2f}")
    lines.extend(
        [
            f"possible: {report.possible}",
            f"noise_dropped: {report.noise_dropped}",
            f"enriched: {report.enriched}",
            f"backlog: {report.backlog}",
            f"spend: ${report.spend:.2f}",
            f"sends_by_channel: {report.sends_by_channel}",
            f"bounce_rate: {report.bounce_rate:.4f}",
            f"reply_rate: {report.reply_rate:.4f}",
        ]
    )
    return "\n".join(lines)


def format_runs_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "run_id | created_at | template | possible | noise | enriched | backlog | spend"
    header = (
        "run_id | created_at | template | possible | noise | enriched | backlog | spend"
    )
    body = []
    for row in rows:
        body.append(
            " | ".join(
                (
                    str(row.get("id", "")),
                    str(row.get("created_at", "")),
                    str(row.get("situation_type", "")),
                    str(row.get("possible_count", 0)),
                    str(row.get("noise_dropped", 0)),
                    str(row.get("enriched_count", 0)),
                    str(row.get("backlog_count", 0)),
                    f"{float(row.get('spend_run', 0.0)):.2f}",
                )
            )
        )
    return "\n".join([header, *body])


def format_report_html(report: RunReport) -> str:
    esc = html.escape
    source_rows = "".join(
        f"<tr><td>{esc(name)}</td><td>{calls}</td><td>${cost:.2f}</td></tr>"
        for name, calls, cost in report.sources
    )
    channel_rows = "".join(
        f"<tr><td>{esc(ch)}</td><td>{count}</td></tr>"
        for ch, count in sorted(report.sends_by_channel.items())
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Winnow run {report.run_id}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; line-height: 1.45; }}
table {{ border-collapse: collapse; margin: 0.5rem 0 1rem; }}
th, td {{ border: 1px solid #ccc; padding: 0.35rem 0.6rem; text-align: left; }}
th {{ background: #f4f4f4; }}
</style>
</head>
<body>
<h1>Run {report.run_id}</h1>
<p><strong>created_at:</strong> {esc(report.created_at)}</p>
<p><strong>situation:</strong> {esc(json.dumps(report.situation, sort_keys=True))}</p>
<p><strong>template:</strong> {esc(report.template)}</p>
<p><strong>criteria_names:</strong> {esc(", ".join(report.criteria_names))}</p>
<h2>Counts</h2>
<ul>
<li>possible: {report.possible}</li>
<li>noise_dropped: {report.noise_dropped}</li>
<li>enriched: {report.enriched}</li>
<li>backlog: {report.backlog}</li>
<li>spend: ${report.spend:.2f}</li>
<li>bounce_rate: {report.bounce_rate:.4f}</li>
<li>reply_rate: {report.reply_rate:.4f}</li>
</ul>
<h2>Sources</h2>
<table>
<tr><th>source</th><th>calls</th><th>cost</th></tr>
{source_rows}
</table>
<h2>Sends by channel</h2>
<table>
<tr><th>channel</th><th>sends</th></tr>
{channel_rows}
</table>
</body>
</html>
"""


def write_html_report(report: RunReport, logs_dir: Path | None = None) -> Path:
    base = logs_dir or Path("logs")
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = base / f"report_{stamp}.html"
    path.write_text(format_report_html(report), encoding="utf-8")
    return path


def format_prometheus(report: RunReport | None) -> str:
    if report is None:
        return ""
    rid = str(report.run_id)
    lines = [
        "# HELP winnow_run_possible POSSIBLE candidates for the run",
        "# TYPE winnow_run_possible gauge",
        f'winnow_run_possible{{run_id="{rid}"}} {report.possible}',
        "# HELP winnow_run_noise_dropped NOISE candidates dropped",
        "# TYPE winnow_run_noise_dropped gauge",
        f'winnow_run_noise_dropped{{run_id="{rid}"}} {report.noise_dropped}',
        "# HELP winnow_run_spend_run Spend for the run in USD",
        "# TYPE winnow_run_spend_run gauge",
        f'winnow_run_spend_run{{run_id="{rid}"}} {report.spend}',
        "# HELP winnow_run_bounce_rate Bounced sends divided by sent",
        "# TYPE winnow_run_bounce_rate gauge",
        f'winnow_run_bounce_rate{{run_id="{rid}"}} {report.bounce_rate}',
        "# HELP winnow_run_reply_rate Replies divided by sent",
        "# TYPE winnow_run_reply_rate gauge",
        f'winnow_run_reply_rate{{run_id="{rid}"}} {report.reply_rate}',
    ]
    return "\n".join(lines) + "\n"


def _start_metrics_server() -> None:
    global _METRICS_SERVER
    if _METRICS_SERVER is not None:
        return

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            return

        def do_GET(self) -> None:
            if self.path.rstrip("/") != "/metrics":
                self.send_response(404)
                self.end_headers()
                return
            body = str(_METRICS_SNAPSHOT.get("lines") or "").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    host = os.environ.get("WINNOW_METRICS_HOST", "127.0.0.1").strip() or "127.0.0.1"
    server = HTTPServer((host, metrics_port()), Handler)
    _METRICS_SERVER = server
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


def publish_metrics(report: RunReport | None) -> None:
    if not metrics_enabled():
        return
    _METRICS_SNAPSHOT["lines"] = format_prometheus(report)
    _start_metrics_server()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="winnow.report",
        description="Print Winnow run reports from SQLite (binary counts only)",
    )
    parser.add_argument("--run", type=int, default=None, help="Run id to summarize")
    parser.add_argument(
        "--last",
        type=int,
        default=None,
        help="Print a table of the last N runs",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Write logs/report_<timestamp>.html (self-contained)",
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=None,
        help="Directory for HTML reports (default: logs/)",
    )
    args = parser.parse_args(argv)

    if args.run is None and args.last is None:
        print("Specify --run <id> and/or --last N", file=sys.stderr)
        return 1

    store = WinnowStore(db_path())
    try:
        report: RunReport | None = None
        if args.last is not None:
            table = format_runs_table(store.list_runs(args.last))
            print(table)

        if args.run is not None:
            report = load_run_report(store, args.run)
            print(format_report_text(report))
            if args.html:
                path = write_html_report(report, logs_dir=args.logs_dir)
                print(f"html_path: {path}")

        publish_metrics(report)
        return 0
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())