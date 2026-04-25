"""Tests for the multi-vendor provider layer.

These tests do NOT make real API calls. They verify:
  - Lazy import / lazy auth (constructing a provider with no API key
    must not raise; only `generate()` should).
  - The factory's auto-detection logic.
  - The factory rejects unknown provider names.
  - All providers conform to the LLMProvider Protocol shape.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from compliance_gate.providers import (  # noqa: E402
    GeminiProvider,
    OpenAIProvider,
    get_provider,
)
from compliance_gate.llm import MockProvider, AnthropicProvider  # noqa: E402


class TestProviderShape(unittest.TestCase):
    """Every provider must expose name + model + generate(prompt)."""

    def test_gemini_attributes(self):
        p = GeminiProvider(model="gemini-fake")
        self.assertEqual(p.name, "gemini")
        self.assertEqual(p.model, "gemini-fake")
        self.assertTrue(callable(p.generate))

    def test_openai_attributes(self):
        p = OpenAIProvider(model="gpt-fake")
        self.assertEqual(p.name, "openai")
        self.assertEqual(p.model, "gpt-fake")
        self.assertTrue(callable(p.generate))


class TestLazyAuth(unittest.TestCase):
    """Constructors must NOT touch env or import SDKs.

    This matters because `from compliance_gate import get_provider` runs
    at import time in CI, where API keys are intentionally absent.
    """

    def test_gemini_construct_without_key_ok(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            GeminiProvider()  # must not raise

    def test_openai_construct_without_key_ok(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            OpenAIProvider()  # must not raise

    def test_gemini_generate_without_key_raises(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            p = GeminiProvider()
            with self.assertRaises(RuntimeError):
                p.generate("hi")

    def test_openai_generate_without_key_raises(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            p = OpenAIProvider()
            with self.assertRaises(RuntimeError):
                p.generate("hi")


class TestFactory(unittest.TestCase):
    def test_explicit_mock(self):
        self.assertIsInstance(get_provider("mock"), MockProvider)

    def test_explicit_gemini(self):
        self.assertIsInstance(get_provider("gemini"), GeminiProvider)

    def test_explicit_openai(self):
        self.assertIsInstance(get_provider("openai"), OpenAIProvider)

    def test_explicit_anthropic(self):
        self.assertIsInstance(get_provider("anthropic"), AnthropicProvider)

    def test_case_insensitive(self):
        self.assertIsInstance(get_provider("MOCK"), MockProvider)

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            get_provider("not-a-real-vendor")

    def test_autodetect_falls_back_to_mock(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsInstance(get_provider(), MockProvider)

    def test_autodetect_prefers_anthropic(self):
        with mock.patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-test", "OPENAI_API_KEY": "sk-test"},
            clear=True,
        ):
            self.assertIsInstance(get_provider(), AnthropicProvider)

    def test_autodetect_picks_gemini_when_only_gemini_set(self):
        with mock.patch.dict(
            os.environ, {"GEMINI_API_KEY": "ai-test"}, clear=True
        ):
            self.assertIsInstance(get_provider(), GeminiProvider)


if __name__ == "__main__":
    unittest.main(verbosity=2)
