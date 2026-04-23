# compliance-gate-pattern-demo

[![CI](https://github.com/bensonyangweb3/compliance-gate-pattern-demo/actions/workflows/ci.yml/badge.svg)](https://github.com/bensonyangweb3/compliance-gate-pattern-demo/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Eval: 31/31](https://img.shields.io/badge/eval-31%2F31%20(100%25)-brightgreen.svg)](evals/RESULTS.md)

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

### Concrete leakage scenario (what this pattern prevents)

```
Without gate-first:
  1. BD tool pulls candidate "@alice_chen_bd" from an inbound list.
  2. LLM drafts: "Hi Alice, loved your recent piece on restaking —
     would love to chat about how our Series B plans align with
     your fund's thesis."
  3. Post-hoc check flags @alice_chen_bd as an existing partner.
  4. Draft is discarded BUT: the LLM (and any logging / caching /
     fine-tuning pipeline behind it) has already seen the mapping
     {"@alice_chen_bd" → "existing partner", restaking thesis, Series B}.
  5. Legal has to treat the upstream inference pipeline as an incident.

With gate-first:
  1. BD tool pulls candidate "@alice_chen_bd".
  2. Gate's alias rule fires → ESCALATE, human review required.
  3. LLM is never called. No draft, no prompt, no cache entry.
  4. Audit log records the decision + input_hash + rule metadata
     for compliance review.
```

---

## Architecture

```mermaid
flowchart TD
    A[Candidate Record] --> B{Deterministic Compliance Gate}
    B -->|rule: internal_conflict| C1[team / customer / partner check]
    B -->|rule: watchlist| C2[sanctions / adverse-media / block-list]
    B -->|rule: alias| C3[normalized-handle match against known contacts]
    B -->|rule: prior_contact| C4[cooldown window check]
    C1 & C2 & C3 & C4 --> D[Reduce: REJECT > ESCALATE > PASS]
    D -->|PASS| E[Project minimal fields to Generation Layer]
    D -->|REJECT or ESCALATE| X[STOP — LLM never called]
    E --> F[LLM Generation (Anthropic / mock)]
    F --> G[Draft]
    D --> H[(Audit Log: SQLite + JSON-Schema)]
    G --> H
    X --> H

    classDef gate fill:#dbeafe,stroke:#1e40af,color:#1e3a8a;
    classDef reject fill:#fee2e2,stroke:#b91c1c,color:#991b1b;
    classDef llm fill:#dcfce7,stroke:#15803d,color:#14532d;
    classDef audit fill:#f3e8ff,stroke:#6b21a8,color:#581c87;
    class B,C1,C2,C3,C4,D gate;
    class X reject;
    class E,F,G llm;
    class H audit;
```

Key invariant: **every path ends at the audit log**. Rejects, escalations,
and passes are all recorded, so compliance can prove later that a rule
*could* have fired and didn't.

---

## Quick start

```bash
pip install -r requirements.txt

# 1. Minimal demo — 4 candidates through the gate, no LLM:
python -m examples.example_run

# 2. Full end-to-end with LLM (mock provider, no API key needed):
python -m examples.with_llm_generation

# 3. Real Claude generation (requires ANTHROPIC_API_KEY):
export ANTHROPIC_API_KEY=sk-ant-...
python -m examples.with_llm_generation --provider anthropic

# 4. Run the evaluation suite (31 labeled cases):
python -m evals.run_eval

# 5. Run unit tests:
python -m pytest tests/ -v
```

Inspect the resulting `demo_audit.db` / `demo_llm_audit.db` with any
SQLite browser to see the structured audit records.

---

## Eval results

The eval suite runs 31 labeled synthetic cases covering happy paths,
each rule's rejection / escalation paths, unicode & normalization edge
cases, boundary conditions, multi-rule hits, and near-miss negatives.

| Metric | Value |
|---|---|
| Total cases | 31 |
| Accuracy | 100.0% |
| Audit completeness | 100.0% |
| PASS precision / recall | 100% / 100% |
| REJECT precision / recall | 100% / 100% |
| ESCALATE precision / recall | 100% / 100% |

Full breakdown (including the confusion matrix and per-category results):
[evals/RESULTS.md](evals/RESULTS.md).

The eval harness is the source of truth for gate behavior. The CI pipeline
runs it on every push and **fails the build on any mismatch or audit gap** —
so the README numbers always reflect the current commit.

One representative finding worth surfacing: case `ne-05` (`@bob_k_trading`)
normalizes to the same canonical form as known alias `@bobk_trading`
because handle normalization intentionally strips separators. This is an
anti-evasion property — an attacker can't bypass the alias rule by
inserting underscores. See [SECURITY.md](SECURITY.md) for the full
normalization threat model.

---

## Layout

```
compliance_gate/
  gate.py         Gate orchestrator — runs rules in declared order
  rules.py        Rule implementations (pure functions)
  audit.py        SQLite audit logger with JSON-Schema validation
  llm.py          Provider interface + Anthropic / mock implementations
  schemas.py      Python-side schema constants + loaders
examples/
  example_run.py            Minimal demo — 4 candidates, no LLM
  with_llm_generation.py    End-to-end demo with LLM draft generation
  sample_config.yaml        Synthetic watchlist / conflict / alias data
evals/
  fixtures.py     31 labeled eval cases
  run_eval.py     Eval harness with precision/recall/audit metrics
  RESULTS.md      Rendered eval report (regenerable)
schema/
  audit_record.schema.json  JSON-Schema for every audit row
tests/
  test_gate.py    Unit tests for the rule layer + orchestrator
.github/workflows/
  ci.yml          pytest + eval on every push
SECURITY.md       Threat model, redaction policy, normalization notes
```

---

## Design principles

1. **Deterministic rules are pure functions.** Given the same input,
   always the same decision. No network calls, no randomness. This is
   what makes the gate auditable.
2. **Rules fail closed.** If a rule errors, the gate defaults to
   ESCALATE, not PASS.
3. **Every decision is logged.** Not just rejects — passes are logged
   too, so you can prove later that a rule *could* have fired and
   didn't.
4. **The gate knows nothing about LLMs.** It only produces PASS /
   REJECT / ESCALATE and structured reasoning. The generation layer
   is a separate concern behind an `LLMProvider` interface.
5. **Explicit redaction boundary.** `build_generation_request` is the
   single chokepoint that projects a candidate record onto the fields
   the LLM is allowed to see. Anything not projected is never seen by
   the LLM — even if the gate used it in its decision.
6. **JSON-Schema at the boundary.** Every audit record is validated
   before commit. Schema drift becomes a first-class, detectable event.
7. **Evals are the source of truth.** Behavior claims are backed by
   labeled cases and numbers that regenerate on every commit.

---

## What this repo is NOT

- Not a production BD tool. No scraping, no sending, no integration
  with real CRMs or messaging platforms.
- Not a real watchlist. The bundled watchlist is a synthetic example.
  In a real deployment you'd plug in Chainalysis / TRM / OFAC feeds.
- Not a guarantee of compliance on its own. The gate is a control, not
  a regulator. Production deployments still need legal review, DPIA,
  periodic rule updates, and human review of ESCALATE cases.
- Not affiliated with any employer of the author. This is a personal
  exploration of the pattern, written for a portfolio.

---

## Roadmap

Concrete next steps a production-minded fork would take:

- Replace the in-memory watchlist with a live OFAC SDN + Chainalysis
  Sanctions API integration (cached, rate-limited).
- Add a rule-result precedence config file so `REJECT > ESCALATE > PASS`
  is not hard-coded in `Gate._reduce`.
- Add rule-level metrics (fire rate, false-positive rate per rule from
  human ESCALATE review).
- Structured logging (OpenTelemetry) in addition to the SQLite audit.
- Signed audit rows (HMAC over the payload) so audit tampering is
  detectable.
- Property-based tests (Hypothesis) for the normalization function.

---

## License

MIT. See [LICENSE](LICENSE).

---

## Author

Built by Shih-Hsiang (Benson) Yang as part of a broader exploration
of compliance-first architecture in LLM-augmented BD workflows.

- LinkedIn: https://www.linkedin.com/in/benson-yang-web3/
- Email: h3795592 [at] gmail [dot] com
