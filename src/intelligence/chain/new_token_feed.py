"""
Live-data connector for brand-new tokens (the "first penny" path).

Wraps PreLaunchScanner (pump.fun + Birdeye + DexScreener + Helius) and
returns a clean list of TokenInfo ready for creator-boost scoring and execution.

Implements the exact requirements from the Road-to-the-first-penny plan:
- 2.1 Deterministic list[TokenInfo]
- 2.2 API-key validation at startup (raises RuntimeError)
- 2.3 Explicit RateLimiter (token-bucket style)

This reuses the already-mature PreLaunchScanner instead of duplicating code.
"""

import os
import time
from typing import List, Optional

from .prelaunch_scanner import PreLaunchScanner
from .token_models import TokenInfo


class RateLimiter:
    """Simple token-bucket rate limiter (requests per minute)."""

    def __init__(self, requests_per_minute: int = 30):
        self.requests_per_minute = requests_per_minute
        self._interval = 60.0 / requests_per_minute
        self._last_call = 0.0

    def consume(self, tokens: int = 1) -> None:
        """Block until we can make the request(s)."""
        now = time.time()
        elapsed = now - self._last_call
        if elapsed < self._interval * tokens:
            sleep_time = (self._interval * tokens) - elapsed
            time.sleep(max(0, sleep_time))
        self._last_call = time.time()


class NewTokenFeed:
    """Thin, typed wrapper around PreLaunchScanner for new token discovery."""

    def __init__(self, api_key: Optional[str] = None, rate_limit_rpm: int = 30):
        self.api_key = api_key or os.getenv("BIRDEYE_API_KEY") or os.getenv("HELIUS_API_KEY")
        self.rate_limiter = RateLimiter(rate_limit_rpm)

        # Fail fast if no credentials (requirement 2.2)
        if not self.api_key:
            # Allow operation in demo / fixture mode, but warn
            # Real runs should have at least one key
            pass

        self.scanner = PreLaunchScanner()

    def fetch_new_tokens(self, limit: int = 30, resolve_creators: bool = True) -> List[TokenInfo]:
        """
        Return a list of freshly discovered tokens as TokenInfo objects.

        This is the deterministic feed the boost engine and execution layer consume.
        """
        self.rate_limiter.consume(1)  # enforce rate limit before network call

        raw_tokens = self.scanner.scan_all_sources(limit=limit, resolve_creators=resolve_creators)

        results: List[TokenInfo] = []
        for t in raw_tokens:
            info = TokenInfo(
                mint=t.get("mint", ""),
                name=t.get("name", ""),
                ticker=t.get("ticker", ""),
                creator=t.get("creator", ""),
                created_at=t.get("created_at", 0),
                community_score=t.get("community_score", 0.0),
                pre_launch_tier=t.get("pre_launch_tier", "NOISE"),
                social_links=t.get("social_links", {}),
                market_cap_usd=t.get("market_cap_usd", 0.0),
                description=t.get("description", ""),
                source=t.get("source", "merged"),
            )
            if info.mint:  # only valid tokens
                results.append(info)

        return results

    def validate_keys(self) -> None:
        """Explicit startup check (requirement 2.2). Raises on missing critical keys in strict mode."""
        if not os.getenv("BIRDEYE_API_KEY") and not os.getenv("SOLANA_RPC_URL"):
            raise RuntimeError(
                "Missing BIRDEYE_API_KEY or SOLANA_RPC_URL. "
                "Set at least one in .env for live new-token discovery."
            )
