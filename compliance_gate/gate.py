"""Gate orchestrator.

The Gate runs a declared sequence of pure, deterministic rules against
a candidate record and produces a single Decision: PASS, REJECT, or
ESCALATE.

Rules are pure functions of the shape:

    def rule(candidate: dict, context: dict) -> RuleResult

where RuleResult.decision is one of PASS / REJECT / ESCALATE and
RuleResult.reason is a short human-readable string.

Rules are evaluated in the order given. The first non-PASS result
short-circuits, EXCEPT that ESCALATE can be overridden by a later
REJECT (a REJECT is stronger than an ESCALATE).
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Callable, Iterable


class Decision(str, Enum):
    PASS = "PASS"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


@dataclass
class RuleResult:
    """Result of a single rule evaluation."""

    rule_name: str
    decision: Decision
    reason: str
    metadata: dict = field(default_factory=dict)


@dataclass
class GateResult:
    """Aggregate result of running all rules."""

    candidate_id: str
    decision: Decision
    reason: str
    rule_results: list[RuleResult]
    timestamp: float
    input_hash: str

    def as_audit_record(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "decision": self.decision.value,
            "reason": self.reason,
            "rule_results": [
                {
                    "rule_name": rr.rule_name,
                    "decision": rr.decision.value,
                    "reason": rr.reason,
                    "metadata": rr.metadata,
                }
                for rr in self.rule_results
            ],
            "timestamp": self.timestamp,
            "input_hash": self.input_hash,
        }


Rule = Callable[[dict, dict], RuleResult]


class Gate:
    """Deterministic compliance gate.

    Usage:
        gate = Gate(rules=[rule_conflict, rule_watchlist, ...])
        result = gate.evaluate(candidate, context={})
    """

    def __init__(self, rules: Iterable[Rule]):
        self._rules: list[Rule] = list(rules)
        if not self._rules:
            raise ValueError("Gate requires at least one rule")

    def evaluate(self, candidate: dict, context: dict | None = None) -> GateResult:
        """Run all rules. Rules FAIL CLOSED — exceptions produce ESCALATE."""
        context = context or {}
        results: list[RuleResult] = []

        for rule in self._rules:
            try:
                rr = rule(candidate, context)
            except Exception as e:  # noqa: BLE001 — fail-closed by design
                rr = RuleResult(
                    rule_name=getattr(rule, "__name__", "unknown_rule"),
                    decision=Decision.ESCALATE,
                    reason=f"rule raised {type(e).__name__}: {e}",
                    metadata={"error": True},
                )
            results.append(rr)

        decision, reason = self._reduce(results)
        return GateResult(
            candidate_id=str(candidate.get("id", "")),
            decision=decision,
            reason=reason,
            rule_results=results,
            timestamp=time.time(),
            input_hash=_hash_candidate(candidate),
        )

    @staticmethod
    def _reduce(results: list[RuleResult]) -> tuple[Decision, str]:
        """Combine rule results into a single decision.

        Precedence (highest wins): REJECT > ESCALATE > PASS.
        """
        rejects = [r for r in results if r.decision == Decision.REJECT]
        if rejects:
            return Decision.REJECT, "; ".join(r.reason for r in rejects)

        escalations = [r for r in results if r.decision == Decision.ESCALATE]
        if escalations:
            return Decision.ESCALATE, "; ".join(r.reason for r in escalations)

        return Decision.PASS, "all rules passed"


def _hash_candidate(candidate: dict) -> str:
    """Stable content hash for the candidate record.

    Used in the audit log so we can later prove that a given decision
    was made against a specific input, even if the source record is
    later mutated or deleted.
    """
    payload = json.dumps(candidate, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
