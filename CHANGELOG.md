# Changelog

All notable changes to this project are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to semantic versioning.

The high-level story this changelog tells:

> **v0.1** demonstrated the gate-first pattern with a single LLM
> vendor (Anthropic). **v0.2** generalizes the pattern across vendors
> and adds adversarial coverage so the gate's guarantees are
> verifiable, not just asserted.

## [Unreleased]

### Planned
- Confusables-map step in handle normalization (Cyrillic-vs-Latin
  collisions, see eval case `adv-alias-mixed-script`).
- HMAC-signed audit rows so tampering is detectable.
- OpenTelemetry tracing alongside the SQLite audit.

## [0.2.0] - 2026-04

### Added
- **Vendor-agnostic LLM adapter** (`compliance_gate/providers.py`).
  - `GeminiProvider` — Google Gemini via `google-generativeai`.
  - `OpenAIProvider` — OpenAI via the `openai` v1 SDK.
  - `get_provider(name=None)` factory with env-var auto-detection
    (`ANTHROPIC_API_KEY` → `GEMINI_API_KEY`/`GOOGLE_API_KEY` →
    `OPENAI_API_KEY` → falls back to `MockProvider`).
  - All vendor SDKs are lazy-imported so the base install stays
    one-command (`pip install -r requirements.txt`).
- **14 new adversarial eval cases** in `evals/fixtures.py` covering:
  - Prompt-injection-style payloads in candidate fields.
  - Alias evasion via zero-width spaces and full-width characters.
  - A documented limitation (Cyrillic-vs-Latin confusables — case
    `adv-alias-mixed-script` PASSes today, with a roadmap entry).
  - Cooldown bypass via field-shuffling (clean handle in `twitter`,
    dirty handle in `telegram` — gate must check both).
  - Multi-rule conflict precedence (REJECT must absorb).
  - DoS-shape inputs (1KB handle).
  - Near-miss negatives (false-positives are as costly as
    false-negatives in BD).
- **Multi-vendor eval harness** (`evals/run_llm_eval.py`).
  - Runs every PASS case through every configured provider.
  - Verifies the redaction boundary holds *for each vendor*,
    independently — not as a single property of the gate.
  - Defaults to `mock` only so CI stays free and offline.
- **Feedback-loop submodule** (`compliance_gate/feedback.py`).
  - Records ESCALATE-case outcomes (human reviewer's eventual
    decision) into the same audit DB.
  - Produces a weekly summary surface for compliance review.
  - Critical design choice: feedback **does not auto-modify rules**.
    It surfaces patterns; humans change rules.
- **Production-stub examples** (`examples/production_stubs.py`).
  - OFAC-API-shaped fetch stub (with ETag-cache hint).
  - CRM webhook stub (rate-limited, idempotent).
  - Notes on what to swap in for production.
- **CHANGELOG.md** (this file).

### Changed
- `compliance_gate/__init__.py` re-exports `get_provider`,
  `GeminiProvider`, `OpenAIProvider` so consumers can
  `from compliance_gate import get_provider`.
- Version bumped to `0.2.0`.

### Security
- Provider classes accept API keys *only* via environment variables.
  Constructor-time keys would risk landing in tracebacks and audit
  logs.
- The redaction boundary (`build_generation_request`) is now
  asserted per-vendor in the multi-vendor harness, not just in the
  unit test for `MockProvider`.

## [0.1.0] - 2026-04

### Added
- Initial release demonstrating the compliance-gate-first pattern.
- Pure-function rule engine (`internal_conflict`, `watchlist`,
  `alias`, `prior_contact`).
- `Gate` orchestrator with fail-closed `REJECT > ESCALATE > PASS`
  reduction.
- JSON-Schema-validated SQLite audit logger.
- Anthropic + Mock LLM providers behind an `LLMProvider` Protocol.
- Explicit redaction policy in `build_generation_request`.
- 31 labeled eval cases with 100% accuracy / audit completeness.
- CI workflow running pytest + eval on every push.
- README, SECURITY.md, sample config.
