"""Container health: writable data dirs and SQLite schema at expected revision."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from winnow.store import WinnowStore, db_path


def data_dir() -> Path:
    raw = os.environ.get("WINNOW_DATA_DIR", "").strip()
    if raw:
        return Path(raw)
    return db_path().parent


def logs_dir() -> Path:
    raw = os.environ.get("WINNOW_LOGS_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path("logs")


def assert_directory_writable(path: Path, *, label: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".healthcheck_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeError(f"{label} not writable: {path}") from exc


def check_store_writable() -> None:
    assert_directory_writable(data_dir(), label="data store")
    assert_directory_writable(logs_dir(), label="logs store")


def check_database_schema() -> None:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    store = WinnowStore(path)
    try:
        store.verify_schema_integrity()
    finally:
        store.close()


def run_checks() -> int:
    try:
        check_store_writable()
        check_database_schema()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("healthcheck ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    del argv
    return run_checks()


if __name__ == "__main__":
    raise SystemExit(main())