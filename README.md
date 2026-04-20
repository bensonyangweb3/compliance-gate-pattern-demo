# compliance-gate-pattern-demo

A reference implementation of the **compliance-gate-first pattern** for
LLM-augmented outreach and BD workflows.

**TL;DR:** Run deterministic compliance rules (internal-conflict /
watchlist / alias / prior-contact) *before* any LLM generation touches
the candidate record. Log every decision to an auditable, JSON-Schema-
validated SQLite store. Keep a clean separation between the
**deterministic gate layer** and the **non-deterministic generation
layer** so compliance review is possible.

This repo is a small, self-contained demo — not a production system. It
demonstrates the architectural pattern and provides a working example
that can be audited by compliance reviewers without sharing any real
partner data.

---

## Why this pattern

Most "AI outreach" tools chain the order wrong:

```
bad:   candidate → LLM draft → (maybe) check filters → send
good:  candidate → deterministic gate → LLM draft (only if gate passes) → send
```

The bad order has two failure modes:

1. **Leaked personalization.** The LLM may have already surfaced a
   sensitive detail about the candidate by the time you check
   conflict-of-interest rules.
2. **Unaudited decisions.** Compliance cannot review what the LLM
   "decided" to include, because that logic is implicit in the prompt.

The gate-first order fixes both: if the deterministic gate rejects a
candidate, the LLM never sees the record. If the gate passes, every
input, rule decision, prompt, and output is recorded in the audit log.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Candidate Record (input)                      │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│             Deterministic Compliance Gate (this repo)            │
│                                                                  │
│  rules/internal_conflict.py    → Is this person on our team,     │
│                                   a customer, or an existing      │
│                                   partner contact?                │
│  rules/watchlist.py            → Sanctions / adverse-media /      │
│                                   internal-block list match?      │
│  rules/alias.py                → Same person under a different    │
│                                   handle (normalization)?         │
│  rules/prior_contact.py        → Contacted in the last N days?    │
│                                                                  │
│  → Pass / Reject / Escalate                                      │
└──────────────────────────────────────────────────────────────────┘
                              ↓ (only if Pass)
┌──────────────────────────────────────────────────────────────────┐
│              LLM Generation Layer (out of scope)                 │
│              – receives only gate-approved records –             │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│           SQLite Audit Log (JSON-Schema validated)               │
│           – every gate decision + every draft                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## Quick start

```bash
pip install -r requirements.txt
python -m examples.example_run
```

This runs four synthetic candidate records through the gate and prints
the decisions. Inspect the resulting `demo_audit.db` with any SQLite
browser to see the structured audit records.

---

## Layout

```
compliance_gate/
  gate.py         Gate orchestrator — runs rules in declared order
  rules.py        Rule implementations (pure functions)
  audit.py        SQLite audit logger with JSON-Schema validation
  schemas.py      Python-side schema constants + loaders
examples/
  example_run.py  End-to-end runnable demo with 4 synthetic candidates
  sample_config.yaml
schema/
  audit_record.schema.json   JSON-Schema for every audit row
tests/
  test_gate.py    Unit tests for the rule layer + orchestrator
```

---

## Design principles

1. **Deterministic rules are pure functions.** Given the same input,
   always the same decision. No network calls, no randomness. This is
   what makes the gate auditable.
2. **Rules fail closed.** If a rule errors, the gate defaults to
   Escalate, not Pass.
3. **Every decision is logged.** Not just rejects — passes are logged
   too, so you can prove later that a rule *could* have fired and
   didn't.
4. **The gate knows nothing about LLMs.** It only produces Pass /
   Reject / Escalate and structured reasoning. The generation layer
   is a separate concern.
5. **JSON-Schema at the boundary.** Every audit record is validated
   before commit. Schema drift becomes a first-class, detectable event.

---

## What this repo is NOT

- Not a production BD tool. No scraping, no sending, no integration
  with real CRMs or messaging platforms.
- Not a real watchlist. The bundled watchlist is a synthetic example.
  In a real deployment you'd plug in Chainalysis / TRM / OFAC feeds.
- Not affiliated with any employer of the author. This is a personal
  exploration of the pattern, written for a portfolio.

---

## License

MIT. See [LICENSE](LICENSE).

---

## Author

Built by Shih-Hsiang (Benson) Yang as part of a broader exploration
of compliance-first architecture in LLM-augmented BD workflows.

- LinkedIn: https://www.linkedin.com/in/benson-yang-web3/
- Email: h3795592@gmail.com
