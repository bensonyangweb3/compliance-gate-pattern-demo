"""Tests for the LLM provider interface and redaction policy.

The key property we want to lock down: `build_generation_request`
MUST NOT surface fields that aren't in the explicit projection list,
even when the candidate record contains them. This is the single
chokepoint that protects the LLM from seeing PII.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from compliance_gate.llm import (  # noqa: E402
    MockProvider,
    build_generation_request,
    generate_outreach,
    render_prompt,
)


class TestRedactionPolicy(unittest.TestCase):
    """The LLM must never see fields outside the explicit projection."""

    def test_email_not_in_prompt(self):
        cand = {
            "id": "c1",
            "twitter": "@ok_handle",
            "email": "secret@example.com",
            "public_summary": "builder",
        }
        req = build_generation_request(cand)
        prompt = render_prompt(req)
        self.assertNotIn("secret@example.com", prompt)
        self.assertNotIn(cand["email"], prompt)

    def test_name_not_in_prompt(self):
        cand = {
            "id": "c2",
            "twitter": "@ok_handle",
            "name": "Confidential RealName",
            "public_summary": "builder",
        }
        req = build_generation_request(cand)
        prompt = render_prompt(req)
        self.assertNotIn("Confidential RealName", prompt)

    def test_arbitrary_extra_fields_dropped(self):
        cand = {
            "id": "c3",
            "twitter": "@ok_handle",
            "internal_score": 0.93,
            "internal_notes": "do not share externally",
            "public_summary": "builder",
        }
        req = build_generation_request(cand)
        prompt = render_prompt(req)
        self.assertNotIn("0.93", prompt)
        self.assertNotIn("do not share", prompt)

    def test_handle_preference_twitter_over_telegram(self):
        cand = {"id": "c4", "twitter": "@primary", "telegram": "@secondary"}
        req = build_generation_request(cand)
        self.assertEqual(req.display_handle, "@primary")

    def test_falls_back_to_telegram_when_twitter_missing(self):
        cand = {"id": "c5", "telegram": "@tg_only"}
        req = build_generation_request(cand)
        self.assertEqual(req.display_handle, "@tg_only")

    def test_default_summary_when_missing(self):
        cand = {"id": "c6", "twitter": "@ok"}
        req = build_generation_request(cand)
        self.assertEqual(req.context_summary, "public contributor")


class TestMockProvider(unittest.TestCase):
    def test_mock_is_deterministic(self):
        p = MockProvider()
        a = p.generate("prompt A")
        b = p.generate("prompt B")
        # The mock always returns the same text regardless of prompt.
        # This is intentional — mock is a stub for offline CI, not a fake.
        self.assertEqual(a, b)
        self.assertIn("mock draft", a)

    def test_generate_outreach_round_trip(self):
        cand = {"id": "c7", "twitter": "@sample", "public_summary": "dev"}
        req = build_generation_request(cand)
        result = generate_outreach(MockProvider(), req)
        self.assertEqual(result.candidate_id, "c7")
        self.assertEqual(result.provider, "mock")
        self.assertIn("@sample", result.prompt)
        self.assertGreater(len(result.draft), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
