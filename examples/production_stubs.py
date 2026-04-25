"""Production-shaped stubs for the parts of a real deployment that this
demo deliberately fakes.

This file is **executable but inert**: every external integration is a
stub that returns a hand-crafted response, with notes on what to swap
in for production. The point is to make the contract surface obvious
so a real fork has a one-line replacement target.

Three stubs are demonstrated:

  1. `OFACWatchlistFetcher`
       Real version: scheduled fetch of OFAC SDN list (or Chainalysis /
       TRM Sanctions API), cached on disk with ETag/If-Modified-Since.
       Stub version: returns the same handful of synthetic entries.

  2. `CRMWebhookSink`
       Real version: signed POST to a CRM with at-least-once retry,
       idempotency key per candidate_id, and a circuit breaker.
       Stub version: appends to an in-memory list.

  3. `RateLimiter`
       Real version: token bucket backed by Redis or a managed queue
       so multiple workers share quota.
       Stub version: a single-process token bucket using time.monotonic.

None of these stubs touch the network. None require credentials. They
exist to document the *interface shape* a production fork must
preserve — so the gate's auditability properties survive the upgrade.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 1. Watchlist fetcher
# ---------------------------------------------------------------------------


@dataclass
class WatchlistEntry:
    """Shape of a single watchlist entry, regardless of source."""

    handle: str                         # canonical handle / address / name
    source: str                         # "OFAC" | "Chainalysis" | ...
    category: Optional[str] = None      # "SDN" | "sanctions" | ...
    listed_at: Optional[str] = None     # ISO date the source first listed it
    raw: dict[str, Any] = field(default_factory=dict)


class OFACWatchlistFetcher:
    """Stub for an OFAC SDN list fetcher.

    Production swap-in:
      - Use `requests` / `httpx` to GET the OFAC SDN XML endpoint.
      - Pass `If-None-Match` with the last ETag; cache to disk.
      - Parse to `WatchlistEntry` objects.
      - Return cache-on-error so a transient OFAC outage doesn't take
        down the gate (it should fail-closed at the rule level, not at
        the fetch level).
    """

    SOURCE = "OFAC-SDN-stub"
    SAMPLE: list[dict] = [
        {
            "handle": "@blocked_entity_example",
            "category": "SDN",
            "listed_at": "2024-01-15",
        },
        {
            "handle": "bad.actor@example.invalid",
            "category": "SDN",
            "listed_at": "2024-03-02",
        },
    ]

    def __init__(self, cache_path: str | Path | None = None):
        self._cache_path = Path(cache_path) if cache_path else None

    def fetch(self) -> list[WatchlistEntry]:
        # Production: HTTP GET + ETag, with on-disk cache fallback.
        # Stub: return the canned sample, optionally writing it to the
        # cache path so a downstream consumer can read it like a real
        # cache file.
        out = [
            WatchlistEntry(
                handle=row["handle"],
                source=self.SOURCE,
                category=row["category"],
                listed_at=row["listed_at"],
                raw=row,
            )
            for row in self.SAMPLE
        ]
        if self._cache_path:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps([e.__dict__ for e in out], indent=2)
            )
        return out


# ---------------------------------------------------------------------------
# 2. CRM webhook sink
# ---------------------------------------------------------------------------


class CRMWebhookSink:
    """Stub for a CRM webhook delivery.

    Production swap-in:
      - Sign the payload (HMAC-SHA256 with a per-tenant key).
      - Idempotency key = `audit_row_id` so retries don't double-write.
      - Exponential backoff with jitter; circuit-breaker after N
        consecutive failures (then drop to a dead-letter queue).
      - Never include redacted fields. The audit row is the source of
        truth for what the gate observed; the CRM only needs the
        decision + minimal context.
    """

    def __init__(self):
        self.delivered: list[dict] = []
        self._seen_keys: set[str] = set()

    def deliver(self, audit_row_id: int, payload: dict) -> bool:
        idempotency_key = f"audit:{audit_row_id}"
        if idempotency_key in self._seen_keys:
            return False  # already delivered
        # Production: requests.post(url, headers=..., json=payload, timeout=..)
        self.delivered.append({"key": idempotency_key, "payload": payload})
        self._seen_keys.add(idempotency_key)
        return True


# ---------------------------------------------------------------------------
# 3. Rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Single-process token bucket — illustrative only.

    Production swap-in:
      - Token bucket in Redis (`INCR` + `EXPIRE`) so workers share quota.
      - Per-vendor limits (Anthropic vs Gemini vs OpenAI have different
        free-tier ceilings — the gate's pacing should reflect that).
      - Surface remaining-budget metrics so operators can see when the
        gate will start throttling LLM calls.
    """

    def __init__(self, capacity: int, refill_per_sec: float):
        self.capacity = capacity
        self.refill = refill_per_sec
        self._tokens = float(capacity)
        self._last = time.monotonic()

    def acquire(self, n: int = 1) -> bool:
        now = time.monotonic()
        self._tokens = min(
            self.capacity, self._tokens + (now - self._last) * self.refill
        )
        self._last = now
        if self._tokens >= n:
            self._tokens -= n
            return True
        return False


# ---------------------------------------------------------------------------
# Demo — wires the three stubs together
# ---------------------------------------------------------------------------


def main() -> None:
    print("== production_stubs demo ==")
    fetcher = OFACWatchlistFetcher()
    entries = fetcher.fetch()
    print(f"watchlist: {len(entries)} entries from {fetcher.SOURCE}")

    sink = CRMWebhookSink()
    delivered = sink.deliver(
        audit_row_id=42,
        payload={"decision": "REJECT", "rule": "watchlist"},
    )
    # Same key again — should not double-deliver.
    duplicate = sink.deliver(
        audit_row_id=42,
        payload={"decision": "REJECT", "rule": "watchlist"},
    )
    print(f"crm: first_delivered={delivered}, duplicate_delivered={duplicate}")

    rl = RateLimiter(capacity=5, refill_per_sec=1.0)
    bursts = [rl.acquire() for _ in range(7)]
    print(f"rate_limiter: {sum(bursts)}/7 acquired in burst")


if __name__ == "__main__":
    main()
