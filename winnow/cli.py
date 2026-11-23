"""Command-line entry for dry-run pipeline execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from winnow.orchestrator import run_winnow
from winnow.source_router import resolve_adapters_from_env


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="winnow", description="Winnow binary-only outreach pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Run full dry-run pipeline")
    run_cmd.add_argument(
        "--situation",
        required=True,
        help='Free-text startup situation, e.g. "B2B SaaS launch need CTO in Ghana"',
    )
    run_cmd.add_argument(
        "--audit-log",
        type=Path,
        default=None,
        help="Optional path to append JSONL audit records",
    )
    run_cmd.add_argument(
        "--json",
        action="store_true",
        help="Print RunResult summary as JSON on stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "run":
        parsed_situation = args.situation
        gh_query = parsed_situation
        adapters = resolve_adapters_from_env(github_query=gh_query)
        result = run_winnow(
            parsed_situation,
            adapters,
            audit_log_path=args.audit_log,
        )
        if args.json:
            payload = {
                "situation_type": result.situation_type,
                "criteria_names": result.criteria_names,
                "sources": result.sources,
                "possible_count": len(result.possible),
                "noise_dropped": result.noise_dropped,
                "outreach": {
                    "sent": result.outreach.sent,
                    "replied": result.outreach.replied,
                    "bounced": result.outreach.bounced,
                    "suppressed": result.outreach.suppressed,
                    "skipped": result.outreach.skipped,
                },
            }
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"situation={result.situation_type} possible={len(result.possible)} "
                f"noise_dropped={result.noise_dropped} outreach_sent={result.outreach.sent}"
            )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())