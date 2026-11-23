from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from winnow.models import Candidate
from winnow.store import SCHEMA_REVISION, WinnowStore, db_path


def _candidate(
    *,
    id: str = "c1",
    name: str = "Ada",
    org: str = "OrgCo",
) -> Candidate:
    return Candidate(
        id=id,
        name=name,
        org=org,
        role="CTO",
        signals={"community_member": "yes"},
        contacts={"email": "ada@org.test"},
        source="fixture",
        collected_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_save_noise_raises(tmp_path: Path) -> None:
    store = WinnowStore(tmp_path / "winnow.sqlite")
    with pytest.raises(ValueError, match="NOISE"):
        store.save_candidate(_candidate(), "noise")


def test_resee_updates_last_seen_no_duplicate(tmp_path: Path) -> None:
    store = WinnowStore(tmp_path / "winnow.sqlite")
    first = _candidate(id="id-a", name="Ada", org="OrgCo")
    second = _candidate(id="id-b", name="  ada ", org=" orgco ")
    store.save_candidate(first, "possible")
    first_seen = store._conn.execute(
        "SELECT last_seen FROM candidates WHERE id = ?", ("id-a",)
    ).fetchone()["last_seen"]
    store.save_candidate(second, "possible")
    count = store._conn.execute("SELECT COUNT(*) AS n FROM candidates").fetchone()["n"]
    assert count == 1
    row = store._conn.execute(
        "SELECT id, last_seen FROM candidates WHERE name_norm = 'ada'"
    ).fetchone()
    assert row["id"] == "id-a"
    assert row["last_seen"] >= first_seen


def test_suppression_query_exact(tmp_path: Path) -> None:
    store = WinnowStore(tmp_path / "winnow.sqlite")
    store.save_candidate(_candidate(id="p1"), "possible")
    store.save_candidate(_candidate(id="c1", name="Bob"), "contacted")
    store.save_candidate(_candidate(id="r1", name="Cal"), "replied")
    store.save_candidate(_candidate(id="b1", name="Dan"), "bounced")
    store.save_candidate(_candidate(id="o1", name="Eve"), "opted_out")
    assert store.suppression_ids() == {"c1", "r1", "b1", "o1"}


def test_monthly_spend_sum_matches_rows(tmp_path: Path) -> None:
    store = WinnowStore(tmp_path / "winnow.sqlite")
    store.record_spend(2.5, "2026-11", None)
    store.record_spend(1.0, "2026-11", None)
    store.record_spend(3.0, "2026-10", None)
    assert store.month_spend("2026-11") == pytest.approx(3.5)
    assert store.month_spend("2026-10") == pytest.approx(3.0)


def test_migration_idempotent(tmp_path: Path) -> None:
    spend = tmp_path / "spend.json"
    spend.write_text(
        json.dumps({"period": "2026-11", "month_spent": 12.5}),
        encoding="utf-8",
    )
    suppression = tmp_path / "suppression.txt"
    suppression.write_text("legacy-1\nlegacy-2\n", encoding="utf-8")
    db = tmp_path / "winnow.sqlite"
    store = WinnowStore(db)
    store.migrate_legacy(spend_json=spend, suppression_files=(suppression,))
    assert not spend.exists()
    assert not suppression.exists()
    assert store.month_spend("2026-11") == pytest.approx(12.5)
    assert "legacy-1" in store.suppression_ids()

    spend.write_text(
        json.dumps({"period": "2026-11", "month_spent": 99.0}),
        encoding="utf-8",
    )
    suppression.write_text("legacy-3\n", encoding="utf-8")
    store.migrate_legacy(spend_json=spend, suppression_files=(suppression,))
    assert store.month_spend("2026-11") == pytest.approx(12.5)
    assert "legacy-3" not in store.suppression_ids()


def test_default_db_path() -> None:
    assert db_path() == Path("logs/winnow.sqlite")


def test_schema_revision_recorded_and_verifiable(tmp_path: Path) -> None:
    store = WinnowStore(tmp_path / "winnow.sqlite")
    assert store.schema_revision() == SCHEMA_REVISION
    store.verify_schema_integrity()
    store._set_meta("schema_revision", "0")
    with pytest.raises(RuntimeError, match="schema_revision"):
        store.verify_schema_integrity()
    store.close()