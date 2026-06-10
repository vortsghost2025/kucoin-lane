"""
Polymarket Provider - Prediction Market Intelligence
=====================================================
Fetches real-money prediction market odds from Polymarket (gamma-api).
Crypto-relevant markets provide high-signal sentiment data backed by actual capital.

Key markets for token intelligence:
- Token airdrop probabilities (Pump.fun, Hyperliquid, MegaETH, etc.)
- Exchange listings (Kraken IPO, Binance/Coinbase listings)
- Regulatory outcomes (SEC decisions, capital gains tax, ETF approvals)
- Protocol milestones (mainnet launches, token generations)
- Macro crypto (BTC price levels, ETH staking yields, stablecoin regulation)

Free tier: No API key required, generous rate limits.
"""

import json
import logging
import os
import re
import time
import threading
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

_BASE_URL = "https://gamma-api.polymarket.com"
_MIN_INTERVAL = 0.5  # ~2 req/sec - be respectful
_last_call_ts = 0.0
_lock = threading.Lock()

CRYPTO_EVENT_SLUGS = [
    "pump-fun-airdrop",
    "hyperliquid-airdrop",
    "megaeth-airdrop",
    "trump-eliminates-capital-gains-tax-on-crypto",
    "kraken-ipo",
    "coinbase-listing",  # if exists
    "binance-listing",   # if exists
]

# Use word-boundary regex patterns to avoid false positives like "sol" in "solution"
CRYPTO_PATTERNS = [
    r"\bcrypto\b", r"\bbitcoin\b", r"\bbtc\b", r"\bethereum\b", r"\beth\b", r"\bsolana\b", r"\bsol\b",
    r"\btoken\b", r"\bairdrop\b", r"\bdefi\b", r"\bbinance\b", r"\bcoinbase\b", r"\betf\b", r"\bsec\b",
    r"\bstablecoin\b", r"\bweb3\b", r"\bblockchain\b", r"\bnft\b", r"\bmemecoin\b", r"\bpump\b",
    r"\bhyperliquid\b", r"\bmegaeth\b", r"\bkraken\b", r"\bipo\b", r"\blisting\b",
    r"capital gains", r"\bregulation\b", r"\betf\b", r"\bapproval\b",
    r"\bmainnet\b", r"token generation", r"\btge\b", r"\blaunch\b",
]

_compiled_patterns = [re.compile(p, re.IGNORECASE) for p in CRYPTO_PATTERNS]


def _matches_crypto(text: str) -> bool:
    """Check if text contains crypto-related keywords with word boundaries."""
    if not text:
        return False
    for pattern in _compiled_patterns:
        if pattern.search(text):
            return True
    return False


def _rate_limited_get(url: str, timeout: int = 15) -> bytes:
    global _last_call_ts
    with _lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.monotonic()
    req = Request(url, headers={"User-Agent": "kucoin-lane-polymarket/1.0", "Accept": "application/json"})
    resp = urlopen(req, timeout=timeout)
    return resp.read()


def _safe_get(url: str, retries: int = 3, timeout: int = 15) -> Optional[bytes]:
    for attempt in range(retries):
        try:
            return _rate_limited_get(url, timeout=timeout)
        except HTTPError as e:
            if e.code in (429, 418):
                time.sleep((attempt + 1) * 2)
                continue
            logger.warning("Polymarket HTTP %s for %s", e.code, url)
            return None
        except (URLError, OSError) as e:
            logger.warning("Polymarket network error: %s", e)
            time.sleep((attempt + 1) * 1)
    return None


class PolymarketProvider:
    def __init__(self):
        self._event_cache: Dict[str, Dict] = {}
        self._market_cache: Dict[str, Dict] = {}
        self._cache_ttl = 300  # 5 minutes

    def get_events(self, active_only: bool = True, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch all active events from Polymarket."""
        cache_key = f"events_active_{active_only}_limit_{limit}"
        if cache_key in self._event_cache:
            cached, ts = self._event_cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                return cached

        params = f"active={str(active_only).lower()}&closed=false&limit={limit}"
        url = f"{_BASE_URL}/events?{params}"
        raw = _safe_get(url)
        if not raw:
            return []

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

        self._event_cache[cache_key] = (data, time.time())
        return data

    def get_crypto_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Filter events for crypto-relevant topics."""
        events = self.get_events(active_only=True, limit=limit)
        crypto_events = []
        for event in events:
            title = event.get("title") or ""
            desc = event.get("description") or ""
            if _matches_crypto(title) or _matches_crypto(desc):
                crypto_events.append(event)
        return crypto_events

    def get_event_markets(self, event_slug: str) -> List[Dict[str, Any]]:
        """Get all markets within a specific event."""
        cache_key = f"event_markets_{event_slug}"
        if cache_key in self._market_cache:
            cached, ts = self._market_cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                return cached

        # Markets endpoint supports event filtering
        url = f"{_BASE_URL}/markets?active=true&closed=false&limit=100"
        raw = _safe_get(url)
        if not raw:
            return []

        try:
            all_markets = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

        # Filter markets belonging to this event
        event_markets = []
        for market in all_markets:
            events = market.get("events", [])
            for ev in events:
                if ev.get("slug") == event_slug:
                    event_markets.append(market)
                    break

        self._market_cache[cache_key] = (event_markets, time.time())
        return event_markets

    def get_market_by_slug(self, market_slug: str) -> Optional[Dict[str, Any]]:
        """Find a specific market by slug (search in all active markets)."""
        url = f"{_BASE_URL}/markets?active=true&closed=false&limit=200"
        raw = _safe_get(url)
        if not raw:
            return None

        try:
            markets = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

        for market in markets:
            if market.get("slug") == market_slug:
                return market
        return None

    def search_markets(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search markets by keyword in question text."""
        url = f"{_BASE_URL}/markets?active=true&closed=false&limit={limit}&search={query}"
        raw = _safe_get(url)
        if not raw:
            return []

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

        # Client-side filter since search seems broad
        filtered = []
        query_lower = query.lower()
        for market in data:
            question = (market.get("question") or "").lower()
            if query_lower in question:
                filtered.append(market)
        return filtered

    def get_crypto_markets(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all crypto-relevant markets across all events."""
        url = f"{_BASE_URL}/markets?active=true&closed=false&limit={min(limit * 3, 500)}"
        raw = _safe_get(url)
        if not raw:
            return []

        try:
            all_markets = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

        crypto_markets = []
        for market in all_markets:
            question = market.get("question") or ""
            if _matches_crypto(question):
                crypto_markets.append(market)
                if len(crypto_markets) >= limit:
                    break

        return crypto_markets

    def normalize_market(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Polymarket market to internal format."""
        outcomes_raw = market.get("outcomes", [])
        if isinstance(outcomes_raw, str):
            try:
                outcomes = json.loads(outcomes_raw)
            except (json.JSONDecodeError, TypeError):
                outcomes = []
        else:
            outcomes = outcomes_raw

        prices_str = market.get("outcomePrices", "[]")
        try:
            prices = json.loads(prices_str)
        except (json.JSONDecodeError, TypeError):
            prices = []

        # Yes/No markets - get Yes price
        yes_price = 0.0
        no_price = 0.0
        if outcomes and prices:
            yes_idx = outcomes.index("Yes") if "Yes" in outcomes else 0
            no_idx = outcomes.index("No") if "No" in outcomes else (1 if len(prices) > 1 else 0)
            yes_price = float(prices[yes_idx]) if yes_idx < len(prices) else 0.0
            no_price = float(prices[no_idx]) if no_idx < len(prices) else 0.0

        events = market.get("events", [])
        event_title = events[0].get("title") if events else ""

        return {
            "source": "polymarket",
            "market_id": market.get("id"),
            "question": market.get("question"),
            "slug": market.get("slug"),
            "event_title": event_title,
            "outcomes": outcomes,
            "yes_price": yes_price,
            "no_price": no_price,
            "spread": abs(yes_price - (1.0 - no_price)) if (yes_price and no_price) else 0.0,
            "volume": float(market.get("volume", 0) or 0),
            "volume_24h": float(market.get("volume24hr", 0) or 0),
            "volume_1w": float(market.get("volume1wk", 0) or 0),
            "volume_1m": float(market.get("volume1mo", 0) or 0),
            "liquidity": float(market.get("liquidity", 0) or 0),
            "end_date": market.get("endDate"),
            "end_date_iso": market.get("endDateIso"),
            "active": market.get("active", False),
            "closed": market.get("closed", False),
            "last_trade_price": float(market.get("lastTradePrice", 0) or 0),
            "best_bid": float(market.get("bestBid", 0) or 0),
            "best_ask": float(market.get("bestAsk", 0) or 0),
            "one_day_change": float(market.get("oneDayPriceChange", 0) or 0),
            "one_week_change": float(market.get("oneWeekPriceChange", 0) or 0),
            "clob_token_ids": market.get("clobTokenIds", []),
        }

    def get_airdrop_odds(self) -> Dict[str, Dict]:
        """Get odds for known token airdrop markets."""
        # Actual slugs from Polymarket API (with typos preserved)
        airdrop_events = {
            "pumpfun-airdop-by": "Pump.fun",
            "hyperliquid-airdop-by": "Hyperliquid",
            "megaeth-airdrop-by": "MegaETH",
        }
        result = {}
        for slug, name in airdrop_events.items():
            markets = self.get_event_markets(slug)
            if markets:
                normalized = [self.normalize_market(m) for m in markets]
                # Find the main "will airdrop by X date" market
                main_market = None
                for m in normalized:
                    q = (m.get("question") or "").lower()
                    if "airdrop" in q and ("by" in q or "before" in q):
                        main_market = m
                        break
                if not main_market and normalized:
                    main_market = normalized[0]
                if main_market:
                    result[name] = main_market
        return result

    def get_regulatory_odds(self) -> Dict[str, Dict]:
        """Get odds for regulatory/policy markets."""
        reg_keywords = ["sec", "etf", "capital gains", "regulation", "ban", "approve", "law", "bill", "trump", "crypto"]
        markets = self.get_crypto_markets(limit=100)
        result = {}
        for market in markets:
            norm = self.normalize_market(market)
            q = (norm.get("question") or "").lower()
            if any(kw in q for kw in reg_keywords):
                result[norm.get("question", "")[:80]] = norm
        return result


# Singleton instance
_provider_instance: Optional[PolymarketProvider] = None


def get_polymarket_provider() -> PolymarketProvider:
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = PolymarketProvider()
    return _provider_instance