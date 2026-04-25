"""Tests for the feedback module.

The feedback log is intentionally simple: insert review rows, query
them back. The tests lock down:
  - Schema is created on first open.
  - Bad final_decision values are rejected.
  - summarize_recent buckets correctly.
  - The log doesn't auto-modify rules (no such API exists).
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from compliance_gate.feedback import FeedbackLog  # noqa: E402


class TestFeedbackLog(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "fb.db"

    def tearDown(self):
        self._tmp.cleanup()

    def test_record_and_read(self):
        with FeedbackLog(self.db) as fb:
            rid = fb.record_review(
                audit_row_id=1,
                reviewer="alice@example.com",
                final_decision="PASS",
                notes="false positive on alias rule",
            )
            self.assertGreater(rid, 0)
            rows = fb.all_reviews()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["final_decision"], "PASS")

    def test_invalid_decision_rejected(self):
        with FeedbackLog(self.db) as fb:
            with self.assertRaises(ValueError):
                fb.record_review(
                    audit_row_id=1,
                    reviewer="alice@example.com",
                    final_decision="ESCALATE",  # not allowed at review time
                )

    def test_summarize_recent_counts_buckets(self):
        with FeedbackLog(self.db) as fb:
            fb.record_review(1, "alice@example.com", "PASS")
            fb.record_review(2, "alice@example.com", "REJECT")
            fb.record_review(3, "bob@example.com", "REJECT")
            summary = fb.summarize_recent(days=7)
            self.assertEqual(summary["total_reviews"], 3)
            self.assertEqual(summary["overturned_to_pass"], 1)
            self.assertEqual(summary["confirmed_reject"], 2)
            self.assertEqual(summary["by_reviewer"]["alice@example.com"], 2)
            self.assertEqual(summary["by_reviewer"]["bob@example.com"], 1)

    def test_no_auto_rule_modification_api(self):
        """Locks in the design choice: feedback never modifies rules.

        If someone later adds a `mutate_rules` / `auto_update` method,
        this test fails — forcing a code review on the design change.
        """
        with FeedbackLog(self.db) as fb:
            forbidden = (
                "mutate_rules", "update_rules", "auto_update",
                "rewrite_rules", "patch_rules", "apply_to_rules",
            )
            for attr in forbidden:
                self.assertFalse(
                    hasattr(fb, attr),
                    f"FeedbackLog must not expose {attr!r} — "
                    "rule changes go through human-reviewed PRs.",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
