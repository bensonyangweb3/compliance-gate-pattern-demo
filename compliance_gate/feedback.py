"""Human-in-the-loop feedback module.

Purpose: when the gate returns ESCALATE, a human reviews the case and
eventually decides PASS or REJECT. We want to record those decisions so
that:

  1. Compliance has a paper trail of human overrides.
  2. We can compute the false-positive rate of each rule (how often
     ESCALATE became PASS in human review).
  3. We can spot drift — e.g. a rule that used to escalate 5/week now
     escalates 50/week.

Design choice (deliberate): **feedback does NOT auto-modify rules.**
Letting an LLM-augmented system rewrite its own compliance rules is
exactly the failure mode the gate-first pattern exists to prevent.
This module surfaces patterns; humans change rules.

API:

    fb = FeedbackLog(db_path)
    fb.record_review(
        audit_row_id=42,
        reviewer="alice@example.com",
        final_decision="PASS",
        notes="False positive — different person with similar handle.",
    )
    summary = fb.summarize_recent(days=7)

The schema is intentionally separate from the main audit table so
write paths can't be confused. Foreign-key linkage is by audit_row_id.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_row_id    INTEGER NOT NULL,
    reviewer        TEXT NOT NULL,
    final_decision  TEXT NOT NULL CHECK(final_decision IN ('PASS','REJECT')),
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS reviews_audit_row_id_idx
    ON reviews(audit_row_id);
CREATE INDEX IF NOT EXISTS reviews_created_at_idx
    ON reviews(created_at);
"""


@dataclass
class ReviewRecord:
    audit_row_id: int
    reviewer: str
    final_decision: str
    notes: Optional[str] = None


class FeedbackLog:
    """SQLite-backed human-review log.

    Lifecycle: open via context manager OR call `close()` explicitly.
    Safe to instantiate alongside `AuditLogger` on the same DB file —
    each writes to its own table.
    """

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ----- writers -----
    def record_review(
        self,
        audit_row_id: int,
        reviewer: str,
        final_decision: str,
        notes: Optional[str] = None,
    ) -> int:
        if final_decision not in ("PASS", "REJECT"):
            raise ValueError(
                "final_decision must be 'PASS' or 'REJECT' "
                "(an ESCALATE outcome would mean the review didn't happen)."
            )
        cur = self._conn.execute(
            "INSERT INTO reviews (audit_row_id, reviewer, final_decision, notes) "
            "VALUES (?, ?, ?, ?)",
            (audit_row_id, reviewer, final_decision, notes),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    # ----- readers -----
    def all_reviews(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT id, audit_row_id, reviewer, final_decision, notes, created_at "
            "FROM reviews ORDER BY id"
        )
        return [
            {
                "id": r[0],
                "audit_row_id": r[1],
                "reviewer": r[2],
                "final_decision": r[3],
                "notes": r[4],
                "created_at": r[5],
            }
            for r in cur.fetchall()
        ]

    def summarize_recent(self, days: int = 7) -> dict:
        """Aggregate reviews from the last N days.

        Returns:
          {
            "window_days":          int,
            "total_reviews":        int,
            "overturned_to_pass":   int   # ESCALATE → PASS
            "confirmed_reject":     int   # ESCALATE → REJECT
            "by_reviewer":          {reviewer: count, ...},
          }
        """
        since = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).strftime("%Y-%m-%dT%H:%M:%S")
        cur = self._conn.execute(
            "SELECT reviewer, final_decision FROM reviews "
            "WHERE created_at >= ?",
            (since,),
        )
        rows = cur.fetchall()
        by_reviewer: dict[str, int] = {}
        overturned = 0
        confirmed = 0
        for reviewer, decision in rows:
            by_reviewer[reviewer] = by_reviewer.get(reviewer, 0) + 1
            if decision == "PASS":
                overturned += 1
            elif decision == "REJECT":
                confirmed += 1
        return {
            "window_days": days,
            "total_reviews": len(rows),
            "overturned_to_pass": overturned,
            "confirmed_reject": confirmed,
            "by_reviewer": by_reviewer,
        }

    # ----- lifecycle -----
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "FeedbackLog":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


@contextmanager
def open_feedback(db_path: str | Path) -> Iterable[FeedbackLog]:
    fb = FeedbackLog(db_path)
    try:
        yield fb
    finally:
        fb.close()


__all__ = ["FeedbackLog", "ReviewRecord", "open_feedback"]
