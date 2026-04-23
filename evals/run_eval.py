"""Eval runner — measures gate behavior against a labeled dataset.

Metrics produced:

  - accuracy                    overall fraction of correct decisions
  - per-class precision/recall  for PASS, REJECT, ESCALATE
  - confusion matrix            expected × actual
  - audit completeness          fraction of cases that produced an
                                audit row (target: 1.00)
  - failure list                the actual mismatches, if any

The script exits non-zero on any mismatch — that lets CI wire it up
as a test gate.

Run:
    python -m evals.run_eval

Produce markdown report (for the README):
    python -m evals.run_eval --format markdown > evals/RESULTS.md
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from compliance_gate import AuditLogger, Gate, load_rules  # noqa: E402
from evals.fixtures import EVAL_CASES, EVAL_CONTEXT  # noqa: E402


DECISIONS = ("PASS", "REJECT", "ESCALATE")


def run() -> dict:
    """Run every fixture through the gate and collect per-case results."""
    gate = Gate(rules=load_rules())
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "eval_audit.db"
        with AuditLogger(db_path) as audit:
            rows: list[dict] = []
            for case in EVAL_CASES:
                result = gate.evaluate(case["candidate"], context=EVAL_CONTEXT)
                audit_row_id = audit.log(result.as_audit_record())
                rows.append(
                    {
                        "id": case["id"],
                        "category": case["category"],
                        "expected": case["expected"],
                        "actual": result.decision.value,
                        "reason": result.reason,
                        "audit_row_id": audit_row_id,
                        "note": case["note"],
                    }
                )
            audit_count = audit.count()

    total = len(rows)
    correct = sum(1 for r in rows if r["expected"] == r["actual"])
    mismatches = [r for r in rows if r["expected"] != r["actual"]]

    # Confusion matrix
    confusion: dict[str, Counter] = {d: Counter() for d in DECISIONS}
    for r in rows:
        confusion[r["expected"]][r["actual"]] += 1

    # Per-class precision / recall
    per_class: dict[str, dict[str, float]] = {}
    for d in DECISIONS:
        tp = sum(1 for r in rows if r["expected"] == d and r["actual"] == d)
        fp = sum(1 for r in rows if r["expected"] != d and r["actual"] == d)
        fn = sum(1 for r in rows if r["expected"] == d and r["actual"] != d)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        per_class[d] = {
            "precision": precision,
            "recall": recall,
            "support": sum(1 for r in rows if r["expected"] == d),
        }

    audit_completeness = audit_count / total if total else 0.0

    return {
        "rows": rows,
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "mismatches": mismatches,
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "per_class": per_class,
        "audit_completeness": audit_completeness,
    }


# ---------------------------------------------------------------------------
# Reporters
# ---------------------------------------------------------------------------


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def report_text(res: dict) -> str:
    lines = []
    lines.append(f"Ran {res['total']} cases")
    lines.append(f"  correct              : {res['correct']}/{res['total']}")
    lines.append(f"  accuracy             : {_fmt_pct(res['accuracy'])}")
    lines.append(f"  audit completeness   : {_fmt_pct(res['audit_completeness'])}")
    lines.append("")
    lines.append("Per-class:")
    lines.append(f"  {'class':<10} {'precision':>10} {'recall':>10} {'support':>8}")
    for d, m in res["per_class"].items():
        lines.append(
            f"  {d:<10} {_fmt_pct(m['precision']):>10} "
            f"{_fmt_pct(m['recall']):>10} {m['support']:>8}"
        )
    lines.append("")
    lines.append("Confusion matrix (rows=expected, cols=actual):")
    lines.append(f"  {'':<10} " + " ".join(f"{d:>10}" for d in DECISIONS))
    for exp in DECISIONS:
        row = res["confusion"][exp]
        lines.append(
            f"  {exp:<10} " + " ".join(f"{row.get(act, 0):>10}" for act in DECISIONS)
        )
    lines.append("")
    if res["mismatches"]:
        lines.append(f"MISMATCHES ({len(res['mismatches'])}):")
        for r in res["mismatches"]:
            lines.append(
                f"  {r['id']}: expected {r['expected']}, got {r['actual']} "
                f"— {r['note']}"
            )
    else:
        lines.append("No mismatches. All cases passed.")
    return "\n".join(lines)


def report_markdown(res: dict) -> str:
    lines = []
    lines.append("# Eval Results")
    lines.append("")
    lines.append(
        f"- **Total cases:** {res['total']}  \n"
        f"- **Accuracy:** {_fmt_pct(res['accuracy'])}  \n"
        f"- **Audit completeness:** {_fmt_pct(res['audit_completeness'])}"
    )
    lines.append("")
    lines.append("## Per-class metrics")
    lines.append("")
    lines.append("| Class | Precision | Recall | Support |")
    lines.append("|---|---:|---:|---:|")
    for d, m in res["per_class"].items():
        lines.append(
            f"| {d} | {_fmt_pct(m['precision'])} "
            f"| {_fmt_pct(m['recall'])} | {m['support']} |"
        )
    lines.append("")
    lines.append("## Confusion matrix")
    lines.append("")
    lines.append("| expected \\ actual | " + " | ".join(DECISIONS) + " |")
    lines.append("|---|" + "|".join(["---:"] * len(DECISIONS)) + "|")
    for exp in DECISIONS:
        row = res["confusion"][exp]
        lines.append(
            f"| **{exp}** | "
            + " | ".join(str(row.get(act, 0)) for act in DECISIONS)
            + " |"
        )
    lines.append("")
    lines.append("## Case breakdown by category")
    lines.append("")
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in res["rows"]:
        by_cat[r["category"]].append(r)
    lines.append("| Category | Cases | Correct |")
    lines.append("|---|---:|---:|")
    for cat, rows in sorted(by_cat.items()):
        ok = sum(1 for r in rows if r["expected"] == r["actual"])
        lines.append(f"| {cat} | {len(rows)} | {ok} |")
    lines.append("")
    if res["mismatches"]:
        lines.append("## Mismatches")
        lines.append("")
        for r in res["mismatches"]:
            lines.append(
                f"- `{r['id']}` — expected **{r['expected']}**, "
                f"got **{r['actual']}** — {r['note']}"
            )
    else:
        lines.append("_No mismatches. All cases passed._")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--format", choices=["text", "markdown"], default="text",
        help="Output format. 'markdown' is suitable for piping into RESULTS.md.",
    )
    parser.add_argument(
        "--strict", action="store_true", default=True,
        help="Exit non-zero if any case mismatches or audit completeness < 100%%.",
    )
    parser.add_argument(
        "--no-strict", action="store_false", dest="strict",
        help="Disable strict mode (report only).",
    )
    args = parser.parse_args(argv)

    res = run()
    if args.format == "markdown":
        print(report_markdown(res))
    else:
        print(report_text(res))

    if args.strict:
        if res["mismatches"] or res["audit_completeness"] < 1.0:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
