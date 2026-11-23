"""``python -m winnow.privacy export|erase --candidate-id``."""

from __future__ import annotations

import argparse
import json
import sys

from winnow.privacy import erase_candidate, export_candidate
from winnow.store import WinnowStore, db_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="winnow.privacy")
    sub = parser.add_subparsers(dest="command", required=True)

    export_p = sub.add_parser("export", help="Export PII for a candidate (JSON)")
    export_p.add_argument("--candidate-id", required=True)

    erase_p = sub.add_parser("erase", help="GDPR erasure; keep hashed suppression marker")
    erase_p.add_argument("--candidate-id", required=True)

    args = parser.parse_args(argv)
    store = WinnowStore(db_path())
    try:
        if args.command == "export":
            payload = export_candidate(store, args.candidate_id)
            json.dump(payload, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0
        erase_candidate(store, args.candidate_id)
        print(f"erased PII for {args.candidate_id}")
        return 0
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())