"""End-to-end runnable demo.

Runs four synthetic candidate records through the compliance gate and
prints the per-candidate decision + aggregated stats. All decisions
are also persisted to a SQLite audit log at ./demo_audit.db (gitignored).

Usage:
    python -m examples.example_run

Expected output (abridged):

    [1] cand-001 (Clean Prospect)            -> PASS      all rules passed
    [2] cand-002 (Internal Teammate)         -> REJECT    matches internal conflict list ...
    [3] cand-003 (Watchlist Hit)             -> REJECT    watchlist hit on handle=...
    [4] cand-004 (Known Alias)               -> ESCALATE  handle=... matches known alias ...

    Audit log now contains 4 records at demo_audit.db
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Make the package importable when running as `python examples/example_run.py`
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from compliance_gate import AuditLogger, Gate, load_rules  # noqa: E402


CONFIG_PATH = REPO_ROOT / "examples" / "sample_config.yaml"
DB_PATH = REPO_ROOT / "demo_audit.db"


SYNTHETIC_CANDIDATES = [
    {
        "id": "cand-001",
        "label": "Clean Prospect",
        "name": "Carol Wang",
        "twitter": "@carol_defi",
        "telegram": "@carol_w",
        "email": "carol@example.com",
    },
    {
        "id": "cand-002",
        "label": "Internal Teammate",
        "name": "Alice Teammate",
        "twitter": "@alice_teammate",
        "email": "alice@ourcompany.com",
    },
    {
        "id": "cand-003",
        "label": "Watchlist Hit",
        "name": "Blocked Entity",
        "twitter": "@blocked_entity_example",
        "email": "blocked@example.invalid",
    },
    {
        "id": "cand-004",
        "label": "Known Alias",
        "name": "Alice C.",
        "twitter": "@Alice_Chen_BD",  # case/format variant of a known alias
        "email": "alice.c@example.com",
    },
]


def main() -> int:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        context = yaml.safe_load(f)

    gate = Gate(rules=load_rules())

    # Fresh DB per run — keeps the demo deterministic
    if DB_PATH.exists():
        DB_PATH.unlink()

    with AuditLogger(DB_PATH) as audit:
        for i, cand in enumerate(SYNTHETIC_CANDIDATES, start=1):
            result = gate.evaluate(cand, context=context)
            audit.log(result.as_audit_record())
            print(
                f"[{i}] {cand['id']} ({cand['label']:<24}) -> "
                f"{result.decision.value:<8} {result.reason}"
            )

        print()
        print(f"Audit log now contains {audit.count()} records at {DB_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
