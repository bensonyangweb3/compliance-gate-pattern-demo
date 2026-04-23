"""LLM provider interface + a mock provider for offline runs.

The gate layer knows nothing about LLMs. The *generation* layer does,
but we keep it behind a thin interface so:

1. The example can run without an API key (mock provider).
2. Tests don't make network calls.
3. Swapping Anthropic for another provider is a one-line change.

Anyone wiring this to a real LLM should read SECURITY.md first — the
gate's guarantees only hold if the LLM is called *after* a PASS
decision and *only* with gate-approved fields.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


@dataclass
class GenerationRequest:
    """Inputs to the generation layer.

    Deliberately minimal. The gate decides what the LLM gets to see —
    we do NOT pass the full candidate record here. See
    `build_generation_request` for the redaction policy.
    """

    candidate_id: str
    display_handle: str      # already-sanitized public handle
    context_summary: str      # short, non-PII summary (e.g. "DeFi researcher")
    intent: str               # the outreach intent (e.g. "introduce partnership")


@dataclass
class GenerationResult:
    """Output of the generation layer."""

    candidate_id: str
    provider: str             # "anthropic" | "mock" | ...
    model: str
    prompt: str               # the exact prompt sent (for audit)
    draft: str                # the generated outreach text


class LLMProvider(Protocol):
    """Minimal provider interface. Implementations MUST be pure with
    respect to the inputs (i.e. the prompt + model) — no hidden state,
    no silent retries with different prompts. This keeps the audit
    trail honest.
    """

    name: str
    model: str

    def generate(self, prompt: str) -> str: ...


class MockProvider:
    """Deterministic stub. Returns a canned response shaped like a
    real outreach draft. Useful for offline CI runs and unit tests.
    """

    name = "mock"
    model = "mock-1"

    def generate(self, prompt: str) -> str:
        return (
            "Hi there,\n\n"
            "Saw your work in the DeFi research space and wanted to "
            "reach out about a possible collaboration. Happy to share "
            "more context on a quick call if it sounds relevant.\n\n"
            "Best,\n"
            "BD Team\n"
            "\n"
            "[mock draft — no API call was made]"
        )


class AnthropicProvider:
    """Real Claude provider. Lazily imports `anthropic` so the demo
    can run in environments without it installed. Requires
    ANTHROPIC_API_KEY in the environment.
    """

    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-5", max_tokens: int = 400):
        self.model = model
        self._max_tokens = max_tokens
        self._client = None  # lazy

    def _ensure_client(self):
        if self._client is None:
            try:
                import anthropic  # type: ignore
            except ImportError as e:
                raise RuntimeError(
                    "anthropic SDK not installed. "
                    "Run `pip install anthropic` or use MockProvider."
                ) from e
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError(
                    "ANTHROPIC_API_KEY not set. "
                    "Export it or use MockProvider for offline runs."
                )
            self._client = anthropic.Anthropic()
        return self._client

    def generate(self, prompt: str) -> str:
        client = self._ensure_client()
        msg = client.messages.create(
            model=self.model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        # Anthropic returns a list of content blocks; concatenate text blocks.
        parts = []
        for block in msg.content:
            # block has .type and .text for text blocks
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "".join(parts).strip()


# ---------------------------------------------------------------------------
# Redaction policy
# ---------------------------------------------------------------------------


def build_generation_request(
    candidate: dict, intent: str = "introduce partnership"
) -> GenerationRequest:
    """Project a full candidate record onto the minimal fields the LLM
    is allowed to see.

    This is the *explicit* boundary between the gate layer and the
    generation layer. If a field is not projected here, the LLM never
    sees it — even though the gate may have used it in its decision.

    Policy (intentionally conservative):
      - Pass public handle only (prefer twitter > telegram).
      - Pass a short, already-prepared context summary if present.
      - NEVER pass email, phone, internal notes, or scoring data.
    """
    handle = candidate.get("twitter") or candidate.get("telegram") or candidate.get("handle") or ""
    summary = candidate.get("public_summary") or "public contributor"
    return GenerationRequest(
        candidate_id=str(candidate.get("id", "")),
        display_handle=handle,
        context_summary=summary,
        intent=intent,
    )


PROMPT_TEMPLATE = """\
You are drafting a short, professional BD outreach message to a public \
contributor in the crypto / web3 space. The recipient has already been \
cleared by an independent compliance gate — you do NOT need to repeat \
compliance checks.

Recipient public handle: {display_handle}
Public context: {context_summary}
Outreach intent: {intent}

Rules:
- 3 short paragraphs max. Plain text. No markdown.
- Do NOT invent facts about the recipient beyond the context above.
- Do NOT reference compensation, price, or legal terms.
- Sign off as "BD Team".
"""


def render_prompt(req: GenerationRequest) -> str:
    """Render the outreach prompt. Kept as a pure function so the
    audit log can record the exact prompt bytes that produced a draft.
    """
    return PROMPT_TEMPLATE.format(
        display_handle=req.display_handle,
        context_summary=req.context_summary,
        intent=req.intent,
    )


def generate_outreach(
    provider: LLMProvider, req: GenerationRequest
) -> GenerationResult:
    """Run the provider and wrap the result with full provenance."""
    prompt = render_prompt(req)
    draft = provider.generate(prompt)
    return GenerationResult(
        candidate_id=req.candidate_id,
        provider=provider.name,
        model=provider.model,
        prompt=prompt,
        draft=draft,
    )
