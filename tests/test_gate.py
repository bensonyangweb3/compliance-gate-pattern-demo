"""Unit tests for the gate + rules + audit layer.

Run with:
    python -m pytest tests/ -v

Or without pytest:
    python -m tests.test_gate
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from compliance_gate import AuditLogger, Decision, Gate, load_rules  # noqa: E402
from compliance_gate.rules import (  # noqa: E402
    _normalize_handle,
    rule_alias,
    rule_internal_conflict,
    rule_prior_contact,
    rule_watchlist,
)


class TestNormalizeHandle(unittest.TestCase):
    def test_collisions(self):
        # All of these should produce the same canonical form.
        forms = ["@Alice_01", "alice01", "ALICE 01", " @alice_01 ", "alice.01"]
        canonicals = {_normalize_handle(f) for f in forms}
        self.assertEqual(canonicals, {"alice01"})

    def test_empty_input(self):
        self.assertEqual(_normalize_handle(""), "")
        self.assertEqual(_normalize_handle(None), "")

    def test_unicode_nfkc(self):
        # Full-width digit '１' should fold to '1'.
        self.assertEqual(_normalize_handle("alice０１"), "alice01")


class TestIndividualRules(unittest.TestCase):
    def setUp(self):
        self.context = {
            "cooldown_days": 30,
            "internal_conflicts": ["@alice_teammate"],
            "watchlist": ["@blocked_entity"],
            "known_aliases": {"Alice Chen": "@alice_chen_bd"},
            "prior_contacts_days_ago": {"@recent": 7, "@old": 95},
        }

    def test_internal_conflict_rejects(self):
        cand = {"id": "x", "twitter": "@alice_teammate"}
        rr = rule_internal_conflict(cand, self.context)
        self.assertEqual(rr.decision, Decision.REJECT)

    def test_internal_conflict_passes_clean(self):
        cand = {"id": "x", "twitter": "@clean_prospect"}
        rr = rule_internal_conflict(cand, self.context)
        self.assertEqual(rr.decision, Decision.PASS)

    def test_watchlist_rejects(self):
        cand = {"id": "x", "twitter": "@blocked_entity"}
        rr = rule_watchlist(cand, self.context)
        self.assertEqual(rr.decision, Decision.REJECT)

    def test_alias_escalates(self):
        cand = {"id": "x", "twitter": "@Alice_Chen_BD"}  # case variant
        rr = rule_alias(cand, self.context)
        self.assertEqual(rr.decision, Decision.ESCALATE)

    def test_prior_contact_rejects_within_cooldown(self):
        cand = {"id": "x", "twitter": "@recent"}
        rr = rule_prior_contact(cand, self.context)
        self.assertEqual(rr.decision, Decision.REJECT)

    def test_prior_contact_passes_after_cooldown(self):
        cand = {"id": "x", "twitter": "@old"}
        rr = rule_prior_contact(cand, self.context)
        self.assertEqual(rr.decision, Decision.PASS)


class TestGateReduction(unittest.TestCase):
    """The gate must combine rule results deterministically.

    Precedence: REJECT > ESCALATE > PASS.
    """

    def setUp(self):
        self.gate = Gate(rules=load_rules())
        self.context = {
            "cooldown_days": 30,
            "internal_conflicts": ["@alice_teammate"],
            "watchlist": ["@blocked_entity"],
            "known_aliases": {"Alice Chen": "@alice_chen_bd"},
            "prior_contacts_days_ago": {"@recent": 7},
        }

    def test_pass_when_clean(self):
        cand = {"id": "c1", "twitter": "@carol_defi"}
        r = self.gate.evaluate(cand, self.context)
        self.assertEqual(r.decision, Decision.PASS)

    def test_reject_beats_escalate(self):
        # Candidate hits BOTH alias (escalate) AND watchlist (reject).
        # Reject must win.
        cand = {
            "id": "c2",
            "twitter": "@blocked_entity",
            "telegram": "@alice_chen_bd",
        }
        r = self.gate.evaluate(cand, self.context)
        self.assertEqual(r.decision, Decision.REJECT)

    def test_fail_closed_on_rule_exception(self):
        def broken_rule(_cand, _ctx):
            raise RuntimeError("simulated failure")

        gate = Gate(rules=[broken_rule])
        r = gate.evaluate({"id": "x"}, {})
        self.assertEqual(r.decision, Decision.ESCALATE)
        self.assertIn("simulated failure", r.reason)


class TestAuditLogger(unittest.TestCase):
    def test_valid_record_persists(self):
        gate = Gate(rules=load_rules())
        result = gate.evaluate({"id": "a1", "twitter": "@clean"}, context={})
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "audit.db"
            with AuditLogger(db) as audit:
                row_id = audit.log(result.as_audit_record())
                self.assertEqual(audit.count(), 1)
                self.assertGreater(row_id, 0)

    def test_invalid_record_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "audit.db"
            with AuditLogger(db) as audit:
                bad = {"candidate_id": "x"}  # missing required fields
                with self.assertRaises(ValueError):
                    audit.log(bad)
                self.assertEqual(audit.count(), 0)

    def test_input_hash_is_sha256(self):
        gate = Gate(rules=load_rules())
        result = gate.evaluate({"id": "a1", "twitter": "@clean"}, context={})
        h = result.input_hash
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in h))


if __name__ == "__main__":
    unittest.main(verbosity=2)
