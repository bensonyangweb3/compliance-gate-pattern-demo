"""Eval fixtures: synthetic candidate records with expected gate decisions.

Each case is a dict with:
  - id:            stable id for the case
  - category:      happy_path | conflict | watchlist | alias | cooldown | edge
  - candidate:     the input record to run through the gate
  - expected:      "PASS" | "REJECT" | "ESCALATE"
  - note:          short description of what the case is testing

The eval runner asserts that gate(candidate) == expected and also that
a matching audit row is produced for every case.

Cases are deliberately designed to cover:
  - Clean passes (with and without optional fields)
  - Single-rule rejects
  - Multi-rule hits (REJECT must beat ESCALATE)
  - Unicode / normalization edge cases (full-width digits, emoji in name)
  - Empty / missing fields (must not crash)
  - Prior-contact window boundaries (exactly at cooldown vs under)
"""
from __future__ import annotations

# A single shared context is used for the eval run so that cases can
# reference each other's "internal_conflicts" / "watchlist" etc.
EVAL_CONTEXT = {
    "cooldown_days": 30,
    "internal_conflicts": [
        "@alice_teammate",
        "@bob_internal",
        "support@ourcompany.com",
    ],
    "watchlist": [
        "@blocked_entity_example",
        "@sanctioned_one",
        "bad.actor@example.invalid",
    ],
    "known_aliases": {
        "Alice Chen (existing partner)": "@alice_chen_bd",
        "Bob K. (prior contact, Q3 2025)": "@bobk_trading",
    },
    "prior_contacts_days_ago": {
        "@recent_prospect": 7,
        "@edge_prospect": 30,   # exactly at cooldown — should PASS (< not <=)
        "@older_prospect": 95,
    },
}


EVAL_CASES: list[dict] = [
    # -----------------------------------------------------------------
    # Happy paths (clean PASS)
    # -----------------------------------------------------------------
    {
        "id": "hp-01",
        "category": "happy_path",
        "expected": "PASS",
        "note": "fully-specified clean candidate",
        "candidate": {
            "id": "hp-01",
            "name": "Carol Wang",
            "twitter": "@carol_defi",
            "telegram": "@carol_w",
            "email": "carol@example.com",
        },
    },
    {
        "id": "hp-02",
        "category": "happy_path",
        "expected": "PASS",
        "note": "twitter-only candidate",
        "candidate": {"id": "hp-02", "twitter": "@just_twitter"},
    },
    {
        "id": "hp-03",
        "category": "happy_path",
        "expected": "PASS",
        "note": "email-only candidate",
        "candidate": {"id": "hp-03", "email": "clean@example.com"},
    },
    {
        "id": "hp-04",
        "category": "happy_path",
        "expected": "PASS",
        "note": "handle with dots and dashes that normalize cleanly",
        "candidate": {"id": "hp-04", "twitter": "@new.prospect-01"},
    },
    {
        "id": "hp-05",
        "category": "happy_path",
        "expected": "PASS",
        "note": "prior contact older than cooldown should still PASS",
        "candidate": {"id": "hp-05", "twitter": "@older_prospect"},
    },
    # -----------------------------------------------------------------
    # Internal conflict rejects
    # -----------------------------------------------------------------
    {
        "id": "ic-01",
        "category": "conflict",
        "expected": "REJECT",
        "note": "exact match on internal conflict list",
        "candidate": {"id": "ic-01", "twitter": "@alice_teammate"},
    },
    {
        "id": "ic-02",
        "category": "conflict",
        "expected": "REJECT",
        "note": "case-variant match — 'ALICE_TEAMMATE'",
        "candidate": {"id": "ic-02", "twitter": "ALICE_TEAMMATE"},
    },
    {
        "id": "ic-03",
        "category": "conflict",
        "expected": "REJECT",
        "note": "dot-separated variant — 'alice.teammate'",
        "candidate": {"id": "ic-03", "twitter": "alice.teammate"},
    },
    {
        "id": "ic-04",
        "category": "conflict",
        "expected": "REJECT",
        "note": "email match on ourcompany domain",
        "candidate": {"id": "ic-04", "email": "support@ourcompany.com"},
    },
    # -----------------------------------------------------------------
    # Watchlist rejects
    # -----------------------------------------------------------------
    {
        "id": "wl-01",
        "category": "watchlist",
        "expected": "REJECT",
        "note": "exact watchlist hit",
        "candidate": {"id": "wl-01", "twitter": "@blocked_entity_example"},
    },
    {
        "id": "wl-02",
        "category": "watchlist",
        "expected": "REJECT",
        "note": "watchlist hit via telegram field",
        "candidate": {"id": "wl-02", "telegram": "@sanctioned_one"},
    },
    {
        "id": "wl-03",
        "category": "watchlist",
        "expected": "REJECT",
        "note": "sanctioned email",
        "candidate": {"id": "wl-03", "email": "bad.actor@example.invalid"},
    },
    # -----------------------------------------------------------------
    # Alias escalations
    # -----------------------------------------------------------------
    {
        "id": "al-01",
        "category": "alias",
        "expected": "ESCALATE",
        "note": "case-variant of known alias",
        "candidate": {"id": "al-01", "twitter": "@Alice_Chen_BD"},
    },
    {
        "id": "al-02",
        "category": "alias",
        "expected": "ESCALATE",
        "note": "known alias via telegram",
        "candidate": {"id": "al-02", "telegram": "@bobk_trading"},
    },
    # -----------------------------------------------------------------
    # Cooldown
    # -----------------------------------------------------------------
    {
        "id": "cd-01",
        "category": "cooldown",
        "expected": "REJECT",
        "note": "contacted 7 days ago — inside 30d cooldown",
        "candidate": {"id": "cd-01", "twitter": "@recent_prospect"},
    },
    {
        "id": "cd-02",
        "category": "cooldown",
        "expected": "PASS",
        "note": "contacted exactly 30 days ago — boundary (< not <=)",
        "candidate": {"id": "cd-02", "twitter": "@edge_prospect"},
    },
    {
        "id": "cd-03",
        "category": "cooldown",
        "expected": "PASS",
        "note": "contacted 95 days ago — well outside cooldown",
        "candidate": {"id": "cd-03", "twitter": "@older_prospect"},
    },
    # -----------------------------------------------------------------
    # Multi-rule hits — REJECT must beat ESCALATE
    # -----------------------------------------------------------------
    {
        "id": "mr-01",
        "category": "edge",
        "expected": "REJECT",
        "note": "watchlist (reject) + alias (escalate) — reject wins",
        "candidate": {
            "id": "mr-01",
            "twitter": "@blocked_entity_example",
            "telegram": "@alice_chen_bd",
        },
    },
    {
        "id": "mr-02",
        "category": "edge",
        "expected": "REJECT",
        "note": "internal (reject) + watchlist (reject) — both reject",
        "candidate": {
            "id": "mr-02",
            "twitter": "@alice_teammate",
            "telegram": "@sanctioned_one",
        },
    },
    # -----------------------------------------------------------------
    # Unicode / normalization edge cases
    # -----------------------------------------------------------------
    {
        "id": "uni-01",
        "category": "edge",
        "expected": "REJECT",
        "note": "full-width digits collide with ASCII — alice_teammate",
        "candidate": {"id": "uni-01", "twitter": "@alice＿teammate"},
    },
    {
        "id": "uni-02",
        "category": "edge",
        "expected": "PASS",
        "note": "emoji in display name should not affect handle normalization",
        "candidate": {
            "id": "uni-02",
            "name": "Unique Prospect 🚀",
            "twitter": "@unique_prospect_42",
        },
    },
    {
        "id": "uni-03",
        "category": "edge",
        "expected": "PASS",
        "note": "CJK characters in name — handle still clean",
        "candidate": {
            "id": "uni-03",
            "name": "王小明",
            "twitter": "@wang_xm_defi",
        },
    },
    # -----------------------------------------------------------------
    # Missing / empty fields — must not crash
    # -----------------------------------------------------------------
    {
        "id": "mf-01",
        "category": "edge",
        "expected": "PASS",
        "note": "only id field — gate must not crash on missing handles",
        "candidate": {"id": "mf-01"},
    },
    {
        "id": "mf-02",
        "category": "edge",
        "expected": "PASS",
        "note": "empty-string twitter",
        "candidate": {"id": "mf-02", "twitter": ""},
    },
    {
        "id": "mf-03",
        "category": "edge",
        "expected": "PASS",
        "note": "null twitter",
        "candidate": {"id": "mf-03", "twitter": None},
    },
    # -----------------------------------------------------------------
    # Explicit negatives — 'similar to but not matching'
    # -----------------------------------------------------------------
    {
        "id": "ne-01",
        "category": "happy_path",
        "expected": "PASS",
        "note": "alice_teammate_jr is NOT alice_teammate",
        "candidate": {"id": "ne-01", "twitter": "@alice_teammate_jr"},
    },
    {
        "id": "ne-02",
        "category": "happy_path",
        "expected": "PASS",
        "note": "blocked_entity_beta is NOT blocked_entity_example",
        "candidate": {"id": "ne-02", "twitter": "@blocked_entity_beta"},
    },
    {
        "id": "ne-03",
        "category": "happy_path",
        "expected": "PASS",
        "note": "alice.chen.bd.io (with .io) should not collide with alice_chen_bd",
        "candidate": {"id": "ne-03", "twitter": "@alice.chen.bd.io"},
    },
    {
        "id": "ne-04",
        "category": "happy_path",
        "expected": "PASS",
        "note": "bobby_knight_trading is clearly distinct from bobk_trading",
        "candidate": {"id": "ne-04", "twitter": "@bobby_knight_trading"},
    },
    {
        "id": "ne-05",
        "category": "alias",
        "expected": "ESCALATE",
        "note": (
            "underscore-injection attack: '@bob_k_trading' normalizes to "
            "'bobktrading' just like known alias '@bobk_trading'. "
            "Aggressive normalization is by design — see SECURITY.md."
        ),
        "candidate": {"id": "ne-05", "twitter": "@bob_k_trading"},
    },
    # -----------------------------------------------------------------
    # Repeat-candidate / idempotency check
    # -----------------------------------------------------------------
    {
        "id": "id-01",
        "category": "edge",
        "expected": "PASS",
        "note": "same candidate as hp-01, different id — same decision expected",
        "candidate": {
            "id": "id-01",
            "name": "Carol Wang",
            "twitter": "@carol_defi",
            "telegram": "@carol_w",
            "email": "carol@example.com",
        },
    },
]
