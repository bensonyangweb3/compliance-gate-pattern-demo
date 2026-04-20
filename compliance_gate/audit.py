"""SQLite audit logger with JSON-Schema validation at the boundary.

Every gate decision is persisted as one row. The stored payload is
validated against the AuditRecord JSON-Schema before commit — if a
payload fails validation it is NOT committed, and a validation error
is raised. This is a deliberate choice: schema drift should be a
first-class detectable event, not a silent corruption.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from .schemas import load_audit_record_schema


class AuditLogger:
    """Append-only SQLite audit sink."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._ensure_schema()
        self._validator = Draft202012Validator(load_audit_record_schema())

    # ----- public --------------------------------------------------------

    def log(self, record: dict[str, Any]) -> int:
        """Validate and persist one audit record. Returns the row id."""
        try:
            self._validator.validate(record)
        except ValidationError as e:
            raise ValueError(
                f"audit record failed schema validation: {e.message} "
                f"(at path {list(e.absolute_path)})"
            ) from e

        with self._conn:
            cur = self._conn.execute(
                """
                INSERT INTO audit_log
                    (candidate_id, decision, reason,
                     rule_results_json, timestamp, input_hash, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["candidate_id"],
                    record["decision"],
                    record["reason"],
                    json.dumps(record["rule_results"], ensure_ascii=False),
                    record["timestamp"],
                    record["input_hash"],
                    json.dumps(record, ensure_ascii=False, sort_keys=True),
                ),
            )
        return cur.lastrowid

    def count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM audit_log")
        (n,) = cur.fetchone()
        return int(n)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "AuditLogger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ----- internals -----------------------------------------------------

    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id       TEXT    NOT NULL,
                    decision           TEXT    NOT NULL
                                         CHECK (decision IN ('PASS','REJECT','ESCALATE')),
                    reason             TEXT    NOT NULL,
                    rule_results_json  TEXT    NOT NULL,
                    timestamp          REAL    NOT NULL,
                    input_hash         TEXT    NOT NULL,
                    payload_json       TEXT    NOT NULL,
                    created_at         TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_candidate "
                "ON audit_log (candidate_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_decision "
                "ON audit_log (decision)"
            )
