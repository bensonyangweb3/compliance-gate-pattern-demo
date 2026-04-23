# Security & Threat Model

This doc captures the assumptions, trust boundaries, and known residual
risks of the `compliance-gate-pattern-demo` pattern. It is intended for
reviewers who want to understand what the gate actually guarantees
before adopting the pattern in a production system.

## Trust boundary

The gate sits at exactly **one** trust boundary: _between the candidate
record store and the LLM generation layer_.

```
  (trusted)              (gate boundary)           (less-trusted)
  candidate store  ───►  deterministic gate  ───►  LLM provider  ───►  draft
                                │
                                └───►  audit log (append-only)
```

Everything before the gate (CRM, inbound lists, scrapers) is assumed to
be trusted-but-imperfect. Everything after the gate is assumed to be a
potential leak surface: LLM providers may log, cache, or fine-tune on
anything they see, and a downstream operator may forward a draft before
a human reviews it. The gate's job is to keep the LLM layer **small-
surface** and **auditable**.

## Threats the pattern mitigates

1. **Leaked personalization via LLM log / cache.** By never sending a
   REJECTed or ESCALATEd candidate to the LLM, the mapping `{handle →
   sensitive attribute}` is never observable to the provider. Even
   under worst-case provider behavior (indefinite retention, training
   on traffic), the provider cannot learn about blocked candidates
   through this pipeline.

2. **Silent rule bypass.** Because every rule result is recorded with
   its `rule_name`, `decision`, and metadata, a compliance reviewer can
   prove at audit time that a rule _could_ have fired and _did not_.
   "Rule skipped" is not a possible state.

3. **Post-hoc draft rationalization.** A "check filters after draft"
   pipeline lets reviewers treat the draft as the record of truth.
   Gate-first inverts this: the filter decision is the record, and the
   draft is subordinate to it.

4. **Alias-based evasion of a named-entity block.** Handle
   normalization folds case, NFKC-normalizes unicode, strips leading
   `@`, and removes all non-alphanumeric characters. This means
   `@Alice_Chen_BD`, `alice.chen.bd`, and `alice chen bd` all collide
   on the normalized form — an attacker can't bypass a block by
   inserting separators or changing case. The eval case `ne-05`
   explicitly tests this property.

5. **Rule-layer exceptions.** Rules fail closed — an exception in any
   rule produces `ESCALATE`, not `PASS`. This is tested by
   `test_fail_closed_on_rule_exception`.

## Threats the pattern does NOT mitigate

1. **A compromised context config.** If an attacker can edit
   `sample_config.yaml` (or the production equivalent), they can empty
   the watchlist. Production deployments must treat the context as a
   secret-adjacent artifact: signed, version-controlled, diff-reviewed.

2. **LLM provider exfiltration.** If the LLM itself is adversarial
   (prompt injection via the `public_summary` field, for example), it
   could try to emit sensitive-looking output. The redaction policy in
   `build_generation_request` mitigates input-side leaks; output-side
   sanitization is out of scope for this demo.

3. **Audit log tampering.** The SQLite log is append-only by convention,
   not by cryptography. A production fork should HMAC-sign each row or
   chain row hashes (Merkle-style) so tampering is detectable.

4. **Stale rule data.** Sanctions lists change. A gate with a 30-day-old
   OFAC snapshot is a liability. Production deployments need a freshness
   SLA on every rule data source, plus alerts when a source hasn't
   refreshed.

5. **Bias in synthetic evals.** The 31 eval cases are hand-written. They
   catch regressions but do not prove generalization to real-world
   adversarial inputs. Property-based testing and red-team cases are
   natural next steps.

## Redaction policy

`compliance_gate.llm.build_generation_request` is the single chokepoint
that projects a candidate record onto the fields the LLM is allowed to
see. Today's policy:

| Candidate field    | Passed to LLM? | Why |
|---                 |---             |---|
| `id`               | yes (as candidate_id) | stable reference for audit join |
| `twitter` / `telegram` / `handle` | one, as `display_handle` | public handle only |
| `public_summary`   | yes (verbatim) | caller-controlled short string |
| `name` (display)   | no | avoid surfacing real-name / attestation data |
| `email`            | no | PII + often keyed to internal accounts |
| `phone`            | no | PII |
| any other field    | no (default-deny) | fields not in the projection list are silently dropped |

Adding a new field to the projection is a **policy change**, not an
implementation detail — it should be diff-reviewed.

## Reporting issues

This is a personal portfolio repo, not a maintained security product.
If you spot something interesting in the pattern or in the code, an
issue or an email is fine — contact details are in the README.
