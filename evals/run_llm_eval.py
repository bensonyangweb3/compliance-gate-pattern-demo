"""Multi-vendor LLM eval harness.

Runs the gate over the full fixture set, then for every PASS case asks
each configured LLM provider to draft an outreach message. Records
per-vendor results so we can compare:

  - drafts_generated         did the provider return non-empty text?
  - prompt_redaction_holds   did the provider's prompt stay free of
                             redacted fields (email, internal notes)?
  - mean_draft_length        sanity bound on output length
  - signoff_compliance       does the draft end with "BD Team"?

By default this runs ONLY the MockProvider so CI is free and offline.
Pass `--providers mock,anthropic,gemini,openai` to opt into real API
calls (which require the corresponding API keys in the environment).

The point of this harness is *not* to benchmark vendor quality —
it's to prove that the redaction boundary holds across vendors and
that the gate-first ordering is preserved no matter which LLM is on
the other side.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from compliance_gate import AuditLogger, Gate, load_rules, get_provider  # noqa: E402
from compliance_gate.llm import (  # noqa: E402
    build_generation_request,
    generate_outreach,
)
from evals.fixtures import EVAL_CASES, EVAL_CONTEXT  # noqa: E402


# Fields that the redaction policy says must NEVER appear in a prompt.
# We assert this property holds for every vendor, every PASS case.
REDACTED_FIELDS = ("email", "internal_score", "internal_notes", "name")


def _instantiate(name: str):
    """Wrap get_provider with a friendly error so the harness can keep
    going if e.g. only `mock` is available."""
    try:
        return get_provider(name)
    except RuntimeError as e:
        print(f"  [skip] provider {name!r}: {e}", file=sys.stderr)
        return None


def run(providers: list[str]) -> dict:
    gate = Gate(rules=load_rules())
    instances = {name: _instantiate(name) for name in providers}
    instances = {n: p for n, p in instances.items() if p is not None}
    if not instances:
        return {"providers": {}, "note": "no providers available"}

    summary: dict = {"providers": {n: _empty_metrics() for n in instances}}

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "llm_eval_audit.db"
        with AuditLogger(db_path) as audit:
            for case in EVAL_CASES:
                gate_result = gate.evaluate(case["candidate"], context=EVAL_CONTEXT)
                audit.log(gate_result.as_audit_record())
                if gate_result.decision.value != "PASS":
                    continue

                req = build_generation_request(case["candidate"])

                for vname, provider in instances.items():
                    metrics = summary["providers"][vname]
                    metrics["pass_cases_seen"] += 1

                    # Redaction property: the prompt must not contain any
                    # value from a redacted field on the original record.
                    leaks = _find_leaks(case["candidate"], req)
                    if leaks:
                        metrics["redaction_violations"].append(
                            {"case_id": case["id"], "leaked_fields": leaks}
                        )

                    try:
                        result = generate_outreach(provider, req)
                    except Exception as e:  # noqa: BLE001
                        metrics["errors"].append(
                            {"case_id": case["id"], "error": str(e)[:200]}
                        )
                        continue

                    metrics["drafts_generated"] += 1
                    metrics["total_draft_chars"] += len(result.draft)
                    if "BD Team" in result.draft:
                        metrics["signoff_ok"] += 1

    # Roll up
    for vname, m in summary["providers"].items():
        if m["drafts_generated"]:
            m["mean_draft_length"] = round(
                m["total_draft_chars"] / m["drafts_generated"], 1
            )
        else:
            m["mean_draft_length"] = 0
        m["redaction_holds"] = len(m["redaction_violations"]) == 0

    return summary


def _empty_metrics() -> dict:
    return {
        "pass_cases_seen": 0,
        "drafts_generated": 0,
        "signoff_ok": 0,
        "total_draft_chars": 0,
        "errors": [],
        "redaction_violations": [],
    }


def _find_leaks(candidate: dict, req) -> list[str]:
    """Return the names of redacted fields whose values would have
    appeared in the request (and thus the prompt). Each call is local
    to the request — no state, no I/O."""
    from compliance_gate.llm import render_prompt

    prompt = render_prompt(req)
    leaks = []
    for field in REDACTED_FIELDS:
        v = candidate.get(field)
        if v and str(v) in prompt:
            leaks.append(field)
    return leaks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--providers",
        default="mock",
        help=(
            "Comma-separated list of providers to test. "
            "Default: 'mock' (no API keys, no network). "
            "Real-API options: anthropic, gemini, openai."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
    )
    args = parser.parse_args(argv)

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    res = run(providers)

    if args.format == "json":
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print("Multi-vendor LLM eval")
        print("=" * 60)
        for vname, m in res["providers"].items():
            print(f"\n[{vname}]")
            print(f"  PASS cases seen      : {m['pass_cases_seen']}")
            print(f"  Drafts generated     : {m['drafts_generated']}")
            print(f"  Sign-off compliance  : {m['signoff_ok']}/{m['drafts_generated']}")
            print(f"  Mean draft length    : {m['mean_draft_length']} chars")
            print(f"  Redaction holds      : {m['redaction_holds']}")
            if m["redaction_violations"]:
                print(f"  REDACTION VIOLATIONS : {m['redaction_violations']}")
            if m["errors"]:
                print(f"  Errors               : {len(m['errors'])}")

    # Strict exit: any redaction violation fails CI.
    for m in res["providers"].values():
        if m.get("redaction_violations"):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
