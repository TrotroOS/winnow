"""Cross-run SQLite memory: candidates, runs, sends, spend."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from winnow.models import Candidate

DEFAULT_DB_PATH = Path("logs/winnow.sqlite")

SUPPRESSION_STATUSES = frozenset(
    {"contacted", "replied", "bounced", "opted_out", "opt_out"}
)

ALLOWED_STATUSES = frozenset(
    {"possible", "contacted", "replied", "bounced", "opted_out", "opt_out"}
)


def db_path() -> Path:
    override = os.environ.get("WINNOW_DB_PATH", "").strip()
    if override:
        return Path(override)
    return DEFAULT_DB_PATH


def _normalize_key(value: str) -> str:
    return value.strip().lower()


class WinnowStore:
    """SQLite-backed operator memory (no candidate goodness scores)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS candidates (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                org TEXT NOT NULL,
                name_norm TEXT NOT NULL,
                org_norm TEXT NOT NULL,
                status TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                contacts_json TEXT NOT NULL DEFAULT '{}',
                signals_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(name_norm, org_norm)
            );

            CREATE TABLE IF NOT EXISTS criteria_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name TEXT NOT NULL,
                criteria_names TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                criteria_version_id INTEGER,
                situation_type TEXT NOT NULL,
                possible_count INTEGER NOT NULL DEFAULT 0,
                noise_dropped INTEGER NOT NULL DEFAULT 0,
                spend_run REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (criteria_version_id) REFERENCES criteria_versions(id)
            );

            CREATE TABLE IF NOT EXISTS sends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT NOT NULL,
                run_id INTEGER,
                channel TEXT NOT NULL DEFAULT '',
                template_version TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'sent',
                created_at TEXT NOT NULL,
                FOREIGN KEY (candidate_id) REFERENCES candidates(id),
                FOREIGN KEY (run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS spend (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                cost REAL NOT NULL,
                period TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            );
            """
        )
        self._conn.commit()

    def save_candidate(self, candidate: Candidate, status: str) -> str:
        """Persist a non-NOISE candidate; merge on normalized (name, org)."""
        if status == "noise":
            raise ValueError("cannot persist NOISE candidates")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"invalid candidate status {status!r}")

        now = datetime.now(timezone.utc).isoformat()
        name_norm = _normalize_key(candidate.name)
        org_norm = _normalize_key(candidate.org)
        cur = self._conn.cursor()
        cur.execute(
            """
            SELECT id FROM candidates
            WHERE name_norm = ? AND org_norm = ?
            """,
            (name_norm, org_norm),
        )
        row = cur.fetchone()
        contacts = json.dumps(dict(candidate.contacts))
        signals = json.dumps(dict(candidate.signals))
        if row:
            candidate_id = str(row["id"])
            cur.execute(
                """
                UPDATE candidates
                SET last_seen = ?, status = ?, role = ?, source = ?,
                    contacts_json = ?, signals_json = ?
                WHERE id = ?
                """,
                (
                    now,
                    status,
                    candidate.role,
                    candidate.source,
                    contacts,
                    signals,
                    candidate_id,
                ),
            )
        else:
            candidate_id = candidate.id
            cur.execute(
                """
                INSERT INTO candidates (
                    id, name, org, name_norm, org_norm, status, last_seen,
                    role, source, contacts_json, signals_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    candidate.name,
                    candidate.org,
                    name_norm,
                    org_norm,
                    status,
                    now,
                    candidate.role,
                    candidate.source,
                    contacts,
                    signals,
                ),
            )
        self._conn.commit()
        return candidate_id

    def set_candidate_status(self, candidate_id: str, status: str) -> None:
        if status == "noise":
            raise ValueError("cannot set status to noise")
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE candidates SET status = ?, last_seen = ? WHERE id = ?",
            (status, now, candidate_id),
        )
        self._conn.commit()

    def suppression_ids(self) -> set[str]:
        placeholders = ",".join("?" for _ in SUPPRESSION_STATUSES)
        cur = self._conn.execute(
            f"SELECT id FROM candidates WHERE status IN ({placeholders})",
            tuple(SUPPRESSION_STATUSES),
        )
        return {str(row["id"]) for row in cur.fetchall()}

    def record_criteria_version(
        self, template_name: str, criteria_names: tuple[str, ...]
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO criteria_versions (template_name, criteria_names, created_at)
            VALUES (?, ?, ?)
            """,
            (template_name, json.dumps(list(criteria_names)), now),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def record_run(
        self,
        *,
        criteria_version_id: int,
        situation_type: str,
        possible_count: int,
        noise_dropped: int,
        spend_run: float,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO runs (
                criteria_version_id, situation_type, possible_count,
                noise_dropped, spend_run, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                criteria_version_id,
                situation_type,
                possible_count,
                noise_dropped,
                spend_run,
                now,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def record_send(
        self,
        *,
        candidate_id: str,
        run_id: int | None,
        channel: str,
        template_version: str,
        status: str = "sent",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO sends (
                candidate_id, run_id, channel, template_version, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (candidate_id, run_id, channel, template_version, status, now),
        )
        if status in SUPPRESSION_STATUSES:
            try:
                self.set_candidate_status(candidate_id, status)
            except sqlite3.Error:
                pass
        self._conn.commit()

    def record_spend(
        self, cost: float, period: str, run_id: int | None = None
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO spend (run_id, cost, period, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, cost, period, now),
        )
        self._conn.commit()

    def month_spend(self, period: str) -> float:
        cur = self._conn.execute(
            "SELECT COALESCE(SUM(cost), 0) FROM spend WHERE period = ?",
            (period,),
        )
        row = cur.fetchone()
        return float(row[0] if row else 0.0)

    def _meta(self, key: str) -> str | None:
        cur = self._conn.execute(
            "SELECT value FROM schema_meta WHERE key = ?", (key,)
        )
        row = cur.fetchone()
        return str(row["value"]) if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            """
            INSERT INTO schema_meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self._conn.commit()

    def migrate_legacy(
        self,
        *,
        spend_json: Path | None = None,
        suppression_files: tuple[Path, ...] = (),
    ) -> None:
        """One-time ingest from legacy files; safe to call twice."""
        if spend_json and spend_json.is_file():
            if self._meta("migrated_spend_json") != "done":
                try:
                    raw = json.loads(spend_json.read_text(encoding="utf-8"))
                    period = str(raw.get("period", ""))
                    amount = float(raw.get("month_spent", 0.0))
                    if period and amount > 0:
                        existing = self.month_spend(period)
                        if existing <= 0:
                            self.record_spend(amount, period, run_id=None)
                    spend_json.unlink(missing_ok=True)
                    self._set_meta("migrated_spend_json", "done")
                except (OSError, json.JSONDecodeError, ValueError):
                    self._set_meta("migrated_spend_json", "done")

        for path in suppression_files:
            flag = f"migrated_suppression:{path.resolve()}"
            if self._meta(flag) == "done":
                continue
            if not path.is_file():
                self._set_meta(flag, "done")
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                cid = line.strip()
                if not cid:
                    continue
                self._conn.execute(
                    """
                    INSERT INTO candidates (
                        id, name, org, name_norm, org_norm, status, last_seen
                    ) VALUES (?, ?, ?, ?, ?, 'contacted', ?)
                    ON CONFLICT(name_norm, org_norm) DO UPDATE SET
                        status = 'contacted',
                        last_seen = excluded.last_seen
                    """,
                    (
                        cid,
                        cid,
                        "",
                        _normalize_key(cid),
                        "",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
            self._conn.commit()
            path.unlink(missing_ok=True)
            self._set_meta(flag, "done")