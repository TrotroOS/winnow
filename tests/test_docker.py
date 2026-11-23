"""Docker packaging smoke tests.

CI approach:
- Always run compose/config and healthcheck unit tests (no Docker daemon).
- When ``docker`` is on PATH, optionally build the image and run healthcheck in a container.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from winnow.healthcheck import assert_directory_writable, run_checks
from winnow.scheduler import scheduled_job
from winnow.store import SCHEMA_REVISION, WinnowStore

ROOT = Path(__file__).resolve().parents[1]
DOCKER_AVAILABLE = shutil.which("docker") is not None


def test_compose_file_valid() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "services" in compose
    assert "scheduler" in compose["services"]
    assert "run-once" in compose["services"]
    scheduler = compose["services"]["scheduler"]
    assert scheduler["command"][0] == "python"
    assert "winnow.scheduler" in scheduler["command"][2]


def test_dockerfile_non_root_and_healthcheck() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER winnow" in text
    assert "winnow.healthcheck" in text
    assert "SENDGRID" not in text
    assert "API_KEY" not in text or "no secrets" in text.lower()


def test_healthcheck_fails_on_unwritable_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    logs = tmp_path / "logs"
    logs.mkdir()
    db = data / "winnow.sqlite"
    monkeypatch.setenv("WINNOW_DB_PATH", str(db))
    monkeypatch.setenv("WINNOW_DATA_DIR", str(data))
    monkeypatch.setenv("WINNOW_LOGS_DIR", str(logs))
    WinnowStore(db).close()
    data.chmod(0o500)
    try:
        with pytest.raises(RuntimeError, match="not writable"):
            assert_directory_writable(data, label="data store")
    finally:
        data.chmod(0o700)


def test_healthcheck_fails_when_schema_behind_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    logs = tmp_path / "logs"
    db = data / "winnow.sqlite"
    monkeypatch.setenv("WINNOW_DB_PATH", str(db))
    monkeypatch.setenv("WINNOW_DATA_DIR", str(data))
    monkeypatch.setenv("WINNOW_LOGS_DIR", str(logs))
    WinnowStore(db).close()

    def _behind_migrations(self: WinnowStore) -> None:
        raise RuntimeError(
            f"database schema_revision {self.schema_revision()!r} "
            f"!= expected {SCHEMA_REVISION!r}"
        )

    monkeypatch.setattr(WinnowStore, "verify_schema_integrity", _behind_migrations)
    assert run_checks() == 1


def test_healthcheck_ok_on_fresh_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    logs = tmp_path / "logs"
    db = data / "winnow.sqlite"
    monkeypatch.setenv("WINNOW_DB_PATH", str(db))
    monkeypatch.setenv("WINNOW_DATA_DIR", str(data))
    monkeypatch.setenv("WINNOW_LOGS_DIR", str(logs))
    assert run_checks() == 0
    store = WinnowStore(db)
    assert store.schema_revision() == SCHEMA_REVISION
    store.close()


def test_makefile_backup_creates_restorable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    db = data / "winnow.sqlite"
    store = WinnowStore(db)
    store.close()
    backup_dir = tmp_path / "backups"
    env = {
        **os.environ,
        "WINNOW_DB_PATH": str(db),
        "BACKUP_DIR": str(backup_dir),
        "BACKUP_RETENTION_DAYS": "7",
    }
    result = subprocess.run(
        ["make", "-C", str(ROOT), "backup"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    files = list(backup_dir.glob("winnow_*.db"))
    assert len(files) == 1
    restored = WinnowStore(files[0])
    restored.verify_schema_integrity()
    restored.close()


def test_winnow_halt_stops_scheduler_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import yaml as pyyaml

    cfg = {
        "situation": {
            "situation_type": "community",
            "stage": "seed",
            "product": "Winnow",
            "goal": "grow community",
            "constraint": "time",
            "segment": "devtools",
            "channels": ["email"],
        },
        "sources": ["mock"],
        "daily_cap": 25,
        "max_spend_per_run": 5,
        "max_spend_per_month": 100,
    }
    config = tmp_path / "config.yaml"
    config.write_text(pyyaml.dump(cfg), encoding="utf-8")
    logs = tmp_path / "logs"
    monkeypatch.setenv("WINNOW_HALT", "1")
    monkeypatch.setenv("WINNOW_DB_PATH", str(logs / "winnow.sqlite"))
    code, reason = scheduled_job(config, logs_dir=logs)
    assert code == 0
    assert "WINNOW_HALT" in reason


@pytest.mark.skipif(not DOCKER_AVAILABLE, reason="docker CLI not available")
def test_container_builds_and_healthcheck_exits_zero() -> None:
    tag = "winnow:test-ci"
    build = subprocess.run(
        ["docker", "build", "-t", tag, str(ROOT)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert build.returncode == 0, build.stderr[-2000:]
    run = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-e",
            "WINNOW_DB_PATH=/data/winnow.sqlite",
            "-e",
            "WINNOW_DATA_DIR=/data",
            "-e",
            "WINNOW_LOGS_DIR=/logs",
            tag,
            "python",
            "-m",
            "winnow.healthcheck",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr
    assert "healthcheck ok" in run.stdout