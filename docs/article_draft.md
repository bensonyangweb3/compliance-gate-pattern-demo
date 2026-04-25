# The Compliance-Gate-First Pattern for LLM-Augmented BD Workflows

> Working draft for Medium / dev.to. Targeting ~1500 words, with a working
> repo as the proof-of-life.

## TL;DR

If you're using an LLM to draft sales / BD outreach, **run your
deterministic compliance checks first — before the LLM ever sees the
record.** The opposite order (LLM first, filter after) leaks
personalization into upstream caches you don't control, and it makes
your compliance posture unreviewable. The fix is a small architectural
discipline, not a new tool.

This piece walks through the pattern, the leakage scenario it
prevents, and a working open-source implementation with 45 labeled
eval cases (including 14 adversarial ones) at 100% accuracy.

## The wrong order is the default

Most "AI outreach" stacks I've reviewed look like this:

```
candidate → LLM draft → (maybe) check filters → send
```

The LLM is the first thing that touches the candidate record. It
drafts something personal-sounding ("loved your recent piece on
restaking…"), and only then does a downstream filter ask "wait, is
this person actually on our internal-conflict list?"

There are two problems with this order:

**1. Leaked personalization.** The LLM has already inferred a
relationship between the candidate's identity and a topic of interest.
Even if you discard the draft, that mapping has been processed by an
upstream model — possibly cached, possibly logged, possibly used for
personalization in a future call.

**2. Unauditable decisions.** When compliance asks "what did the
system decide for this candidate, and why?", the answer lives inside
an LLM prompt. Rule logic is implicit, fuzzy, and impossible to
re-run deterministically.

## The right order

```
candidate → deterministic gate → (only on PASS) → LLM → send
```

Three properties make this work:

- **The gate is pure.** Same input, same decision, no network calls.
- **The gate fails closed.** A rule that errors defaults to ESCALATE,
  not PASS.
- **Every path ends at the audit log** — including the rejects, where
  the LLM was never called.

If a candidate is rejected by the gate, the LLM never sees the record.
There's no draft, no prompt, no cache entry. Compliance review reads
the SQLite audit table; everything is reproducible.

## A concrete leakage example

Imagine your inbound list contains `@alice_chen_bd`, who happens to
be an existing partner under a slightly different display name.

In the LLM-first ordering, the LLM has already read the handle and
generated a draft referencing the candidate's recent activity by the
time your alias rule fires. You discard the draft, but the upstream
inference pipeline retains the {handle → topic → relationship} tuple.
Legal now has to treat that pipeline as an incident.

In the gate-first ordering, the alias rule fires *before* the LLM is
called. Decision: ESCALATE. Reviewer queue: 1. LLM calls made: 0.
Audit log: complete. The leak that would have happened didn't.

## The redaction boundary

Even on a PASS, the LLM doesn't see the full record. There's an
explicit projection:

```python
def build_generation_request(candidate, intent="introduce partnership"):
    handle = candidate.get("twitter") or candidate.get("telegram") or ""
    summary = candidate.get("public_summary") or "public contributor"
    return GenerationRequest(
        candidate_id=str(candidate.get("id", "")),
        display_handle=handle,
        context_summary=summary,
        intent=intent,
    )
```

What's missing matters: `email`, `phone`, internal scoring, internal
notes, the entire raw record. None of those reach the LLM, even
though the gate may have used them in its decision. The unit tests
assert this property:

```python
def test_email_not_in_prompt(self):
    cand = {"id": "c1", "twitter": "@ok", "email": "secret@example.com"}
    req = build_generation_request(cand)
    self.assertNotIn("secret@example.com", render_prompt(req))
```

## Verifying it across vendors

The redaction property is interesting only if it holds for every LLM
you might plug in. The repo includes a multi-vendor harness that runs
every PASS case through every configured provider (Anthropic, Gemini,
OpenAI, plus a deterministic mock for offline CI), and asserts the
prompt for every vendor stays free of redacted fields.

```bash
$ python -m evals.run_llm_eval --providers mock
[mock]
  PASS cases seen      : 25
  Drafts generated     : 25
  Sign-off compliance  : 25/25
  Redaction holds      : True
```

CI exits non-zero on any redaction violation. Vendor swaps don't get
to silently weaken the compliance posture.

## Adversarial testing

A gate that only handles benign inputs is a checkbox, not a control.
The eval suite ships 14 adversarial cases — things an attacker might
try if they know there's a gate in front of the LLM:

- Zero-width-space evasion (`@alice​_teammate` should still match
  `@alice_teammate`).
- Full-width-character evasion (`＠Ａlice_chen_bd` should normalize
  to the alias).
- Cooldown bypass via field-shuffling (clean handle in `twitter`,
  recently-contacted handle in `telegram` — gate must check both).
- ID-collision bait (`candidate.id == "@alice_chen_bd"` — gate
  must NOT match against the metadata `id` field).
- Near-miss negatives (`@alice_teammat` — one character short, must
  PASS, because false-positives are as costly as false-negatives in
  BD).

One case is a deliberately documented limitation: Cyrillic 'а' in
`@аlice_chen_bd` doesn't currently collide with the ASCII alias,
because the normalization pass is alphanumerics-only and not
Unicode-confusables-aware. The fix is on the roadmap and the case is
in the eval suite as a tripwire — when we ship the fix, the expected
result flips and the eval will hold us to it.

## What feedback looks like (and doesn't)

The repo includes a feedback module that records the human reviewer's
final decision on every ESCALATE case. That data lets you compute the
false-positive rate per rule, spot drift week-over-week, and make
data-informed updates to the rule set.

What it explicitly does *not* do: auto-modify the rules. Letting an
LLM-augmented system rewrite its own compliance rules is the failure
mode the gate-first pattern exists to prevent. Feedback surfaces
patterns; humans change rules.

## When you don't need this

If you're writing one-off cold emails by hand, this is overkill. The
pattern earns its complexity when:

- You're scaling outreach into the hundreds-per-day range.
- The candidate pool overlaps with internal partners, customers, or
  sanctioned entities.
- Compliance has any reason to want to review your decisions later.

For everyone else, an LLM-first pipeline is fine. The point of this
piece isn't that gates are universally required — it's that *if* you
need one, the order it sits in the pipeline matters more than which
model you're using.

## Repo

Open source, MIT, with a working CI:
[github.com/bensonyangweb3/compliance-gate-pattern-demo](https://github.com/bensonyangweb3/compliance-gate-pattern-demo)

45/45 eval cases passing. Comments, forks, and PRs welcome — especially
on the Cyrillic-confusables work and on additional adversarial cases.
