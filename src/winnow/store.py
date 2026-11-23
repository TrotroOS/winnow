"""Cross-run SQLite memory: candidates, runs, sends, spend."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

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

            CREATE TABLE IF NOT EXISTS adapter_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                adapter TEXT NOT NULL,
                day TEXT NOT NULL,
                run_key TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS adapter_cache (
                adapter TEXT NOT NULL,
                query_key TEXT NOT NULL,
                day TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (adapter, query_key, day)
            );

            CREATE INDEX IF NOT EXISTS idx_adapter_calls_day
                ON adapter_calls(adapter, day);
            CREATE INDEX IF NOT EXISTS idx_adapter_calls_run
                ON adapter_calls(adapter, run_key);
            """
        )
        try:
            cur.execute(
                "ALTER TABLE candidates ADD COLUMN backlog INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass
        self._conn.commit()
        self._ensure_candidate_columns()
        self._ensure_run_columns()
        self._ensure_criteria_version_columns()

    def _ensure_criteria_version_columns(self) -> None:
        cur = self._conn.execute("PRAGMA table_info(criteria_versions)")
        cols = {str(row[1]) for row in cur.fetchall()}
        additions = {
            "generated": "INTEGER NOT NULL DEFAULT 0",
            "approved": "INTEGER NOT NULL DEFAULT 1",
            "proposal_json": "TEXT NOT NULL DEFAULT ''",
        }
        for name, typedef in additions.items():
            if name not in cols:
                self._conn.execute(
                    f"ALTER TABLE criteria_versions ADD COLUMN {name} {typedef}"
                )
        self._conn.commit()

    def _ensure_run_columns(self) -> None:
        cur = self._conn.execute("PRAGMA table_info(runs)")
        cols = {str(row[1]) for row in cur.fetchall()}
        additions = {
            "enriched_count": "INTEGER NOT NULL DEFAULT 0",
            "backlog_count": "INTEGER NOT NULL DEFAULT 0",
            "sources_json": "TEXT NOT NULL DEFAULT '[]'",
            "situation_json": "TEXT NOT NULL DEFAULT '{}'",
            "run_key": "TEXT NOT NULL DEFAULT ''",
            "outreach_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, typedef in additions.items():
            if name not in cols:
                self._conn.execute(
                    f"ALTER TABLE runs ADD COLUMN {name} {typedef}"
                )
        self._conn.commit()

    def _ensure_candidate_columns(self) -> None:
        cur = self._conn.execute("PRAGMA table_info(candidates)")
        cols = {str(row[1]) for row in cur.fetchall()}
        additions = {
            "bounce_attempts": "INTEGER NOT NULL DEFAULT 0",
            "suppression_hash": "TEXT",
            "anonymized_at": "TEXT",
        }
        for name, typedef in additions.items():
            if name not in cols:
                self._conn.execute(
                    f"ALTER TABLE candidates ADD COLUMN {name} {typedef}"
                )
        self._conn.commit()

    def save_candidate(
        self, candidate: Candidate, status: str, *, backlog: bool = False
    ) -> str:
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
                    contacts_json = ?, signals_json = ?, backlog = ?
                WHERE id = ?
                """,
                (
                    now,
                    status,
                    candidate.role,
                    candidate.source,
                    contacts,
                    signals,
                    1 if backlog else 0,
                    candidate_id,
                ),
            )
        else:
            candidate_id = candidate.id
            cur.execute(
                """
                INSERT INTO candidates (
                    id, name, org, name_norm, org_norm, status, last_seen,
                    role, source, contacts_json, signals_json, backlog
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    1 if backlog else 0,
                ),
            )
        self._conn.commit()
        return candidate_id

    def set_backlog(self, candidate_id: str, backlog: bool) -> None:
        self._conn.execute(
            "UPDATE candidates SET backlog = ? WHERE id = ?",
            (1 if backlog else 0, candidate_id),
        )
        self._conn.commit()

    def backlog_candidates(self) -> list[Candidate]:
        cur = self._conn.execute(
            """
            SELECT id, name, org, role, source, contacts_json, signals_json, last_seen
            FROM candidates
            WHERE status = 'possible' AND backlog = 1
            ORDER BY last_seen ASC
            """
        )
        rows: list[Candidate] = []
        for row in cur.fetchall():
            contacts = json.loads(row["contacts_json"] or "{}")
            signals = json.loads(row["signals_json"] or "{}")
            collected_raw = row["last_seen"]
            try:
                collected_at = datetime.fromisoformat(str(collected_raw))
            except ValueError:
                collected_at = datetime.now(timezone.utc)
            rows.append(
                Candidate(
                    id=str(row["id"]),
                    name=str(row["name"]),
                    org=str(row["org"]),
                    role=str(row["role"] or ""),
                    signals={str(k): str(v) for k, v in signals.items()},
                    contacts={str(k): str(v) for k, v in contacts.items()},
                    source=str(row["source"] or ""),
                    collected_at=collected_at,
                )
            )
        return rows

    def adapter_calls_day(self, adapter: str, day: str) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) AS n FROM adapter_calls WHERE adapter = ? AND day = ?",
            (adapter, day),
        )
        row = cur.fetchone()
        return int(row["n"] if row else 0)

    def adapter_calls_run(self, adapter: str, run_key: str) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) AS n FROM adapter_calls WHERE adapter = ? AND run_key = ?",
            (adapter, run_key),
        )
        row = cur.fetchone()
        return int(row["n"] if row else 0)

    def record_adapter_call(self, adapter: str, *, day: str, run_key: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO adapter_calls (adapter, day, run_key, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (adapter, day, run_key, now),
        )
        self._conn.commit()

    def quota_allows(
        self,
        adapter: str,
        *,
        day: str,
        run_key: str,
        per_run: int | None,
        per_day: int | None,
    ) -> tuple[bool, str]:
        if per_run is not None and self.adapter_calls_run(adapter, run_key) >= per_run:
            return False, f"adapter {adapter!r} per-run quota ({per_run}) reached"
        if per_day is not None and self.adapter_calls_day(adapter, day) >= per_day:
            return False, f"adapter {adapter!r} per-day quota ({per_day}) reached"
        return True, ""

    def cache_get(
        self, adapter: str, query_key: str, day: str
    ) -> list[dict[str, object]] | None:
        cur = self._conn.execute(
            """
            SELECT payload FROM adapter_cache
            WHERE adapter = ? AND query_key = ? AND day = ?
            """,
            (adapter, query_key, day),
        )
        row = cur.fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row["payload"])
        except json.JSONDecodeError:
            return None
        if not isinstance(data, list):
            return None
        return [dict(x) for x in data if isinstance(x, dict)]

    def cache_put(
        self,
        adapter: str,
        query_key: str,
        day: str,
        items: list[dict[str, object]],
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO adapter_cache (adapter, query_key, day, payload, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(adapter, query_key, day) DO UPDATE SET
                payload = excluded.payload,
                created_at = excluded.created_at
            """,
            (adapter, query_key, day, json.dumps(items, default=str), now),
        )
        self._conn.commit()

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
        self,
        template_name: str,
        criteria_names: tuple[str, ...],
        *,
        generated: bool = False,
        approved: bool | None = None,
        proposal_json: str = "",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        if approved is None:
            approved = not generated
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO criteria_versions (
                template_name, criteria_names, created_at,
                generated, approved, proposal_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                template_name,
                json.dumps(list(criteria_names)),
                now,
                int(generated),
                int(approved),
                proposal_json,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_criteria_version(self, version_id: int) -> dict[str, Any] | None:
        cur = self._conn.execute(
            """
            SELECT id, template_name, criteria_names, created_at,
                   generated, approved, proposal_json
            FROM criteria_versions WHERE id = ?
            """,
            (version_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "template_name": str(row["template_name"]),
            "criteria_names": json.loads(str(row["criteria_names"])),
            "created_at": str(row["created_at"]),
            "generated": bool(int(row["generated"])),
            "approved": bool(int(row["approved"])),
            "proposal_json": str(row["proposal_json"] or ""),
        }

    def approve_criteria_version(self, version_id: int) -> bool:
        cur = self._conn.execute(
            "SELECT generated FROM criteria_versions WHERE id = ?",
            (version_id,),
        )
        row = cur.fetchone()
        if row is None:
            return False
        self._conn.execute(
            "UPDATE criteria_versions SET approved = 1 WHERE id = ?",
            (version_id,),
        )
        self._conn.commit()
        return True

    def record_run(
        self,
        *,
        criteria_version_id: int,
        situation_type: str,
        possible_count: int,
        noise_dropped: int,
        spend_run: float,
        enriched_count: int = 0,
        backlog_count: int = 0,
        sources: Sequence[str] | None = None,
        situation: dict[str, object] | None = None,
        run_key: str = "",
        outreach: dict[str, int] | None = None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO runs (
                criteria_version_id, situation_type, possible_count,
                noise_dropped, spend_run, created_at,
                enriched_count, backlog_count, sources_json,
                situation_json, run_key, outreach_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                criteria_version_id,
                situation_type,
                possible_count,
                noise_dropped,
                spend_run,
                now,
                enriched_count,
                backlog_count,
                json.dumps(list(sources or ())),
                json.dumps(dict(situation or {})),
                run_key,
                json.dumps(dict(outreach or {})),
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        cur = self._conn.execute(
            """
            SELECT r.*, c.template_name, c.criteria_names
            FROM runs r
            LEFT JOIN criteria_versions c ON c.id = r.criteria_version_id
            WHERE r.id = ?
            """,
            (run_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["criteria_names"] = json.loads(payload.get("criteria_names") or "[]")
        payload["sources"] = json.loads(payload.get("sources_json") or "[]")
        payload["situation"] = json.loads(payload.get("situation_json") or "{}")
        payload["outreach"] = json.loads(payload.get("outreach_json") or "{}")
        return payload

    def list_runs(self, limit: int) -> list[dict[str, Any]]:
        lim = max(1, int(limit))
        cur = self._conn.execute(
            """
            SELECT id, situation_type, possible_count, noise_dropped,
                   spend_run, enriched_count, backlog_count, created_at
            FROM runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (lim,),
        )
        return [dict(row) for row in cur.fetchall()]

    def sends_for_run(self, run_id: int) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            """
            SELECT channel, status, COUNT(*) AS n
            FROM sends
            WHERE run_id = ?
            GROUP BY channel, status
            ORDER BY channel, status
            """,
            (run_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def adapter_calls_by_run_key(self, run_key: str) -> list[dict[str, Any]]:
        if not run_key:
            return []
        cur = self._conn.execute(
            """
            SELECT adapter, COUNT(*) AS calls
            FROM adapter_calls
            WHERE run_key = ?
            GROUP BY adapter
            ORDER BY adapter
            """,
            (run_key,),
        )
        return [dict(row) for row in cur.fetchall()]

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

    def get_candidate_row(self, candidate_id: str) -> dict[str, Any] | None:
        cur = self._conn.execute(
            "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row)

    def increment_bounce_attempts(self, candidate_id: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE candidates
            SET bounce_attempts = bounce_attempts + 1, last_seen = ?
            WHERE id = ?
            """,
            (now, candidate_id),
        )
        self._conn.commit()
        cur = self._conn.execute(
            "SELECT bounce_attempts FROM candidates WHERE id = ?",
            (candidate_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def _hash_for_suppression(self, candidate_id: str) -> str:
        row = self.get_candidate_row(candidate_id)
        material = candidate_id
        if row:
            contacts = json.loads(row.get("contacts_json") or "{}")
            email = str(contacts.get("email", "")).strip().lower()
            if email:
                material = email
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def ensure_suppression_hash(self, candidate_id: str) -> str:
        digest = self._hash_for_suppression(candidate_id)
        self._conn.execute(
            "UPDATE candidates SET suppression_hash = ? WHERE id = ?",
            (digest, candidate_id),
        )
        self._conn.commit()
        return digest

    def erase_candidate_pii(self, candidate_id: str) -> None:
        row = self.get_candidate_row(candidate_id)
        if row is None:
            raise KeyError(f"unknown candidate {candidate_id!r}")
        digest = row.get("suppression_hash") or self._hash_for_suppression(
            candidate_id
        )
        now = datetime.now(timezone.utc).isoformat()
        status = str(row["status"])
        if status not in SUPPRESSION_STATUSES:
            status = "opted_out"
        self._conn.execute(
            """
            UPDATE candidates SET
                name = ?, org = ?, role = ?, source = ?,
                contacts_json = ?, signals_json = ?,
                name_norm = ?, org_norm = ?,
                status = ?, suppression_hash = ?, anonymized_at = ?
            WHERE id = ?
            """,
            (
                "[erased]",
                "",
                "",
                "",
                "{}",
                "{}",
                _normalize_key("[erased]"),
                "",
                status,
                digest,
                now,
                candidate_id,
            ),
        )
        self._conn.commit()

    def anonymize_stale_candidates(
        self,
        inactive_days: int,
        *,
        now: datetime | None = None,
    ) -> int:
        """Anonymize rows with no interaction since ``inactive_days`` ago."""
        if inactive_days < 1:
            return 0
        when = now or datetime.now(timezone.utc)
        cutoff = (when - timedelta(days=inactive_days)).isoformat()
        cur = self._conn.execute(
            """
            SELECT id FROM candidates
            WHERE name != '[erased]'
              AND name != '[anonymized]'
              AND status IN ('possible', 'contacted')
              AND last_seen < ?
              AND NOT EXISTS (
                  SELECT 1 FROM sends s
                  WHERE s.candidate_id = candidates.id
                    AND s.created_at >= ?
              )
            """,
            (cutoff, cutoff),
        )
        ids = [str(row["id"]) for row in cur.fetchall()]
        for cid in ids:
            row = self.get_candidate_row(cid)
            if row is None:
                continue
            digest = row.get("suppression_hash") or self._hash_for_suppression(cid)
            stamped = when.isoformat()
            self._conn.execute(
                """
                UPDATE candidates SET
                    name = ?, org = ?, role = ?,
                    contacts_json = ?, signals_json = ?,
                    name_norm = ?, org_norm = ?,
                    suppression_hash = ?, anonymized_at = ?
                WHERE id = ?
                """,
                (
                    "[anonymized]",
                    "[anonymized]",
                    "",
                    "{}",
                    "{}",
                    _normalize_key("[anonymized]"),
                    _normalize_key("[anonymized]"),
                    digest,
                    stamped,
                    cid,
                ),
            )
        self._conn.commit()
        return len(ids)