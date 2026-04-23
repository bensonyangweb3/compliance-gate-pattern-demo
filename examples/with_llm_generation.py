"""End-to-end example: gate → LLM generation → audit.

This is the full story the gate-first pattern is meant to enable:

    1. Run the deterministic gate on a candidate.
    2. If (and only if) the gate returns PASS, call the LLM.
    3. The LLM only sees a narrowly-projected view of the candidate —
       never the raw record, never PII, never the rule metadata.
    4. Log the LLM prompt + draft alongside the gate decision, so the
       full chain (input → decision → prompt → draft) is auditable.

Run:

    # Mock (no API key needed) — safe default for CI:
    python -m examples.with_llm_generation

    # Real Claude (requires ANTHROPIC_API_KEY):
    python -m examples.with_llm_generation --provider anthropic

Expected output (abridged):

    [cand-101] Clean Prospect        -> PASS       (LLM generated 342 chars)
    [cand-102] Internal Teammate     -> REJECT     (LLM NOT called — gate blocked)
    [cand-103] Watchlist Hit         -> REJECT     (LLM NOT called — gate blocked)

    Audit log contains 3 decisions and 1 generated drafts at demo_llm_audit.db
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from compliance_gate import AuditLogger, Decision, Gate, load_rules  # noqa: E402
from compliance_gate.llm import (  # noqa: E402
    AnthropicProvider,
    MockProvider,
    build_generation_request,
    generate_outreach,
)


CONFIG_PATH = REPO_ROOT / "examples" / "sample_config.yaml"
DB_PATH = REPO_ROOT / "demo_llm_audit.db"


SYNTHETIC_CANDIDATES = [
    {
        "id": "cand-101",
        "label": "Clean Prospect",
        "name": "Carol Wang",
        "twitter": "@carol_defi",
        "telegram": "@carol_w",
        "email": "carol@example.com",
        "public_summary": "independent DeFi researcher, active on Farcaster",
    },
    {
        "id": "cand-102",
        "label": "Internal Teammate",
        "name": "Alice Teammate",
        "twitter": "@alice_teammate",
        "email": "alice@ourcompany.com",
        "public_summary": "internal — should never receive outreach",
    },
    {
        "id": "cand-103",
        "label": "Watchlist Hit",
        "name": "Blocked Entity",
        "twitter": "@blocked_entity_example",
        "email": "blocked@example.invalid",
        "public_summary": "redacted",
    },
]


def _ensure_drafts_table(db_path: Path) -> None:
    """The gate's audit_log table is append-only and schema-locked.
    We keep a separate, side-car table for LLM drafts so we don't
    violate the AuditRecord schema.
    """
    conn = sqlite3.connect(str(db_path))
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_drafts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id TEXT    NOT NULL,
                provider     TEXT    NOT NULL,
                model        TEXT    NOT NULL,
                prompt       TEXT    NOT NULL,
                draft        TEXT    NOT NULL,
                created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (candidate_id) REFERENCES audit_log(candidate_id)
            )
            """
        )
    conn.close()


def _log_draft(db_path: Path, candidate_id: str, result) -> None:
    conn = sqlite3.connect(str(db_path))
    with conn:
        conn.execute(
            "INSERT INTO llm_drafts(candidate_id, provider, model, prompt, draft) "
            "VALUES (?, ?, ?, ?, ?)",
            (candidate_id, result.provider, result.model, result.prompt, result.draft),
        )
    conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--provider",
        choices=["mock", "anthropic"],
        default="mock",
        help="LLM provider. Default: mock (no API key).",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5",
        help="Model name (only used when --provider anthropic).",
    )
    args = parser.parse_args(argv)

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        context = yaml.safe_load(f)

    if args.provider == "anthropic":
        provider = AnthropicProvider(model=args.model)
    else:
        provider = MockProvider()

    gate = Gate(rules=load_rules())
    if DB_PATH.exists():
        DB_PATH.unlink()

    _ensure_drafts_table(DB_PATH)

    drafts_generated = 0
    with AuditLogger(DB_PATH) as audit:
        for cand in SYNTHETIC_CANDIDATES:
            gate_result = gate.evaluate(cand, context=context)
            audit.log(gate_result.as_audit_record())

            if gate_result.decision == Decision.PASS:
                # Only NOW does the LLM see a (redacted) projection of
                # the candidate. If the gate had said REJECT or
                # ESCALATE above, this block would not execute — the
                # LLM never sees the raw record.
                req = build_generation_request(cand)
                gen = generate_outreach(provider, req)
                _log_draft(DB_PATH, cand["id"], gen)
                drafts_generated += 1
                tag = f"(LLM generated {len(gen.draft)} chars)"
            else:
                tag = "(LLM NOT called — gate blocked)"

            print(
                f"[{cand['id']}] {cand['label']:<24} -> "
                f"{gate_result.decision.value:<9} {tag}"
            )

        total = audit.count()

    print()
    print(
        f"Audit log contains {total} decisions and "
        f"{drafts_generated} generated draft(s) at {DB_PATH}"
    )
    print(f"Provider used: {provider.name} / {provider.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
