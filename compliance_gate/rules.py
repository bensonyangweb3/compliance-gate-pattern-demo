"""Rule implementations.

Every rule is a pure function of the shape:

    def rule(candidate: dict, context: dict) -> RuleResult

Rules MUST NOT make network calls, MUST NOT mutate inputs, and SHOULD
be deterministic given a fixed (candidate, context) pair. This is what
makes the gate auditable.

The default rule set in this demo:

    rule_internal_conflict  — is this person an internal teammate, an
                              existing customer, or a prior partner
                              contact? (reject)
    rule_watchlist          — sanctions / adverse-media / internal-
                              block list match? (reject)
    rule_alias              — same person under a different handle?
                              (escalate — human review)
    rule_prior_contact      — contacted in the last N days? (reject
                              with cool-down reason)

`load_rules()` returns the default sequence; consumers can also import
each rule individually and build a custom sequence.
"""
from __future__ import annotations

import unicodedata

from .gate import Decision, Rule, RuleResult


# ----- helpers ---------------------------------------------------------------


def _normalize_handle(raw: str) -> str:
    """Normalize a handle so that 'Alice_01', '@alice01', 'ALICE 01'
    collide.

    Steps:
      1. Unicode NFKC normalize
      2. Lowercase
      3. Strip leading '@'
      4. Remove any non-alphanumeric character
    """
    if raw is None:
        return ""
    s = unicodedata.normalize("NFKC", str(raw)).lower().lstrip("@")
    return "".join(ch for ch in s if ch.isalnum())


def _get_handles(candidate: dict) -> list[str]:
    """Extract all known handles from a candidate, normalized."""
    out: list[str] = []
    for key in ("handle", "twitter", "telegram", "email", "name"):
        v = candidate.get(key)
        if v:
            out.append(_normalize_handle(v))
    return [h for h in out if h]


# ----- rules -----------------------------------------------------------------


def rule_internal_conflict(candidate: dict, context: dict) -> RuleResult:
    """Reject if the candidate overlaps with the internal conflict set."""
    conflict_handles: set[str] = {
        _normalize_handle(h) for h in context.get("internal_conflicts", [])
    }
    for handle in _get_handles(candidate):
        if handle in conflict_handles:
            return RuleResult(
                rule_name="internal_conflict",
                decision=Decision.REJECT,
                reason=f"matches internal conflict list on handle={handle!r}",
                metadata={"matched_handle": handle},
            )
    return RuleResult(
        rule_name="internal_conflict",
        decision=Decision.PASS,
        reason="no match on internal conflict list",
    )


def rule_watchlist(candidate: dict, context: dict) -> RuleResult:
    """Reject if any handle is on the watchlist.

    In a real deployment the watchlist is sourced from Chainalysis /
    TRM / OFAC / internal block lists. Here we accept a simple set.
    """
    watch: set[str] = {_normalize_handle(h) for h in context.get("watchlist", [])}
    for handle in _get_handles(candidate):
        if handle in watch:
            return RuleResult(
                rule_name="watchlist",
                decision=Decision.REJECT,
                reason=f"watchlist hit on handle={handle!r}",
                metadata={"matched_handle": handle, "list_source": "demo"},
            )
    return RuleResult(
        rule_name="watchlist",
        decision=Decision.PASS,
        reason="no match on watchlist",
    )


def rule_alias(candidate: dict, context: dict) -> RuleResult:
    """Escalate if the candidate appears to be an alias of an existing
    contact (fuzzy match on normalized handles).

    This rule intentionally returns ESCALATE rather than REJECT — alias
    matches need human review because they may be false positives.
    """
    known: dict[str, str] = {
        _normalize_handle(h): name
        for name, h in context.get("known_aliases", {}).items()
    }
    for handle in _get_handles(candidate):
        if handle in known:
            return RuleResult(
                rule_name="alias",
                decision=Decision.ESCALATE,
                reason=(
                    f"handle={handle!r} matches known alias of "
                    f"contact={known[handle]!r} — human review required"
                ),
                metadata={
                    "matched_handle": handle,
                    "existing_contact": known[handle],
                },
            )
    return RuleResult(
        rule_name="alias",
        decision=Decision.PASS,
        reason="no alias match",
    )


def rule_prior_contact(candidate: dict, context: dict) -> RuleResult:
    """Reject if the candidate was contacted within the cool-down window."""
    cooldown_days = int(context.get("cooldown_days", 30))
    raw_prior: dict[str, int] = context.get("prior_contacts_days_ago", {})
    # Normalize the keys the same way the candidate handles are normalized
    # so that {"@recent": 7} matches a candidate with twitter="@recent".
    prior: dict[str, int] = {
        _normalize_handle(k): v for k, v in raw_prior.items()
    }
    for handle in _get_handles(candidate):
        days_ago = prior.get(handle)
        if days_ago is not None and days_ago < cooldown_days:
            return RuleResult(
                rule_name="prior_contact",
                decision=Decision.REJECT,
                reason=(
                    f"contacted {days_ago} days ago — "
                    f"cooldown is {cooldown_days} days"
                ),
                metadata={"days_ago": days_ago, "cooldown_days": cooldown_days},
            )
    return RuleResult(
        rule_name="prior_contact",
        decision=Decision.PASS,
        reason=f"no prior contact within {cooldown_days} days",
    )


def load_rules() -> list[Rule]:
    """Default rule sequence. Order matters — see Gate._reduce."""
    return [
        rule_internal_conflict,
        rule_watchlist,
        rule_alias,
        rule_prior_contact,
    ]
