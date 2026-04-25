"""Additional vendor-specific LLM providers.

This module extends `compliance_gate.llm` with non-Anthropic providers.
All providers conform to the `LLMProvider` Protocol declared there:

    class LLMProvider(Protocol):
        name: str
        model: str
        def generate(self, prompt: str) -> str: ...

Design principles (mirrors `llm.AnthropicProvider`):

  * **Lazy imports.** Vendor SDKs are only imported when a provider is
    instantiated *and* its first `generate` call is made. The base
    repo therefore stays installable with `pip install -r requirements.txt`
    even if you only have one (or zero) vendor SDKs.
  * **Env-var auth only.** Providers read their API key from the
    environment. We never accept a key as a constructor argument —
    that keeps keys out of audit logs and tracebacks.
  * **No silent retries / fallbacks.** A provider does exactly what its
    name says. Cross-vendor fallback (e.g. "use OpenAI if Anthropic 429s")
    is the *caller's* concern, not the provider's. This keeps the audit
    trail honest: every recorded `provider` field is the one that actually
    produced the draft.
  * **No prompt mutation.** Providers send the prompt as-is. The redaction
    boundary lives in `llm.build_generation_request`; providers must not
    re-introduce PII via templating.

The `get_provider` factory at the bottom is a convenience for examples
and CI — production code should instantiate providers directly so the
choice is explicit at the call site.
"""
from __future__ import annotations

import os
from typing import Optional


class GeminiProvider:
    """Google Gemini provider.

    Requires:
      - `pip install google-generativeai`
      - GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment

    The default model is a fast, low-cost tier suitable for short
    outreach drafts. Override via the `model` constructor arg.
    """

    name = "gemini"

    def __init__(
        self,
        model: str = "gemini-1.5-flash",
        max_output_tokens: int = 400,
    ):
        self.model = model
        self._max_output_tokens = max_output_tokens
        self._client = None  # lazy

    def _ensure_client(self):
        if self._client is None:
            try:
                import google.generativeai as genai  # type: ignore
            except ImportError as e:
                raise RuntimeError(
                    "google-generativeai SDK not installed. "
                    "Run `pip install google-generativeai` or use MockProvider."
                ) from e
            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get(
                "GOOGLE_API_KEY"
            )
            if not api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY (or GOOGLE_API_KEY) not set. "
                    "Export it or use MockProvider for offline runs."
                )
            genai.configure(api_key=api_key)
            self._client = genai.GenerativeModel(self.model)
        return self._client

    def generate(self, prompt: str) -> str:
        client = self._ensure_client()
        # Lazy import again so the type is available without import at top.
        import google.generativeai as genai  # type: ignore  # noqa: F401

        resp = client.generate_content(
            prompt,
            generation_config={"max_output_tokens": self._max_output_tokens},
        )
        # The SDK exposes a convenience `.text` property that joins all
        # text parts. Fall back to manual extraction if it's missing.
        text = getattr(resp, "text", None)
        if text is None:
            parts = []
            for cand in getattr(resp, "candidates", []) or []:
                content = getattr(cand, "content", None)
                if not content:
                    continue
                for part in getattr(content, "parts", []) or []:
                    t = getattr(part, "text", None)
                    if t:
                        parts.append(t)
            text = "".join(parts)
        return (text or "").strip()


class OpenAIProvider:
    """OpenAI provider.

    Requires:
      - `pip install openai>=1.0`
      - OPENAI_API_KEY in the environment

    Uses the v1 `responses`/`chat.completions` API surface depending on
    SDK version; we use `chat.completions` here for broad compatibility.
    """

    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini", max_tokens: int = 400):
        self.model = model
        self._max_tokens = max_tokens
        self._client = None  # lazy

    def _ensure_client(self):
        if self._client is None:
            try:
                from openai import OpenAI  # type: ignore
            except ImportError as e:
                raise RuntimeError(
                    "openai SDK (>=1.0) not installed. "
                    "Run `pip install openai` or use MockProvider."
                ) from e
            if not os.environ.get("OPENAI_API_KEY"):
                raise RuntimeError(
                    "OPENAI_API_KEY not set. "
                    "Export it or use MockProvider for offline runs."
                )
            self._client = OpenAI()
        return self._client

    def generate(self, prompt: str) -> str:
        client = self._ensure_client()
        resp = client.chat.completions.create(
            model=self.model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        choice = resp.choices[0] if resp.choices else None
        if choice is None:
            return ""
        content = choice.message.content or ""
        return content.strip()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

# Map of provider-name -> zero-arg factory. Kept tiny on purpose; if you
# need vendor-specific config, instantiate the class directly.
_FACTORY = {
    "mock": lambda: _import_mock(),
    "anthropic": lambda: _import_anthropic(),
    "gemini": lambda: GeminiProvider(),
    "openai": lambda: OpenAIProvider(),
}


def _import_mock():
    from .llm import MockProvider

    return MockProvider()


def _import_anthropic():
    from .llm import AnthropicProvider

    return AnthropicProvider()


def get_provider(name: Optional[str] = None):
    """Resolve a provider by name. If name is None, auto-detect by the
    first env var found, falling back to MockProvider.

    Auto-detect order: anthropic > gemini > openai > mock.
    The order is alphabetical-by-stability, not preferential — pick
    explicitly in production.
    """
    if name is None:
        if os.environ.get("ANTHROPIC_API_KEY"):
            name = "anthropic"
        elif os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            name = "gemini"
        elif os.environ.get("OPENAI_API_KEY"):
            name = "openai"
        else:
            name = "mock"

    name = name.lower()
    if name not in _FACTORY:
        raise ValueError(
            f"Unknown provider {name!r}. "
            f"Known: {sorted(_FACTORY.keys())}"
        )
    return _FACTORY[name]()


__all__ = ["GeminiProvider", "OpenAIProvider", "get_provider"]
