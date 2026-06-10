"""
Birdeye Provider - New Token Discovery
======================================
Birdeye API for real-time new token detection on Solana.

Endpoints:
- /defi/token_creation - Newly created tokens (requires API key)
- /defi/token_list - Token list with metadata
- /defi/token_overview - Token overview with social links, creator info

Free tier: 100 requests/minute
Paid tiers: higher limits
"""

import json
import logging
import os
import time
import threading
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

_BASE_URL = "https://public-api.birdeye.so"
_MIN_INTERVAL = 0.6  # ~100 req/min free tier
_last_call_ts = 0.0
_lock = threading.Lock()


def _rate_limited_get(url: str, headers: Dict[str, str], timeout: int = 15) -> bytes:
    global _last_call_ts
    with _lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.monotonic()
    req = Request(url, headers=headers)
    resp = urlopen(req, timeout=timeout)
    return resp.read()


def _safe_get(url: str, headers: Dict[str, str], retries: int = 3, timeout: int = 15) -> Optional[bytes]:
    for attempt in range(retries):
        try:
            return _rate_limited_get(url, headers, timeout=timeout)
        except HTTPError as e:
            if e.code in (429, 418):
                time.sleep((attempt + 1) * 2)
                continue
            logger.warning("Birdeye HTTP %s for %s", e.code, url)
            return None
        except (URLError, OSError) as e:
            logger.warning("Birdeye network error: %s", e)
            time.sleep((attempt + 1) * 1)
    return None


class BirdeyeProvider:
    def __init__(self, chain: str = "solana", api_key: Optional[str] = None):
        self.chain = chain
        self.api_key = api_key or os.getenv("BIRDEYE_API_KEY")
        self.headers = {
            "User-Agent": "kucoin-lane-birdeye/1.0",
            "Accept": "application/json",
        }
        if self.api_key:
            self.headers["X-API-KEY"] = self.api_key
        else:
            logger.warning("Birdeye API key not configured - some endpoints may fail")

    def new_tokens(self, chain: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Get newly created tokens (token_creation_info endpoint)."""
        c = chain or self.chain
        # Try the newer v2 endpoint first
        url = f"{_BASE_URL}/defi/v2/tokens/new_listing?chain={c}&limit={limit}&offset={offset}"
        raw = _safe_get(url, self.headers)
        if raw:
            try:
                data = json.loads(raw)
                items = data.get("data", {}).get("items", []) if isinstance(data.get("data"), dict) else data.get("data", [])
                if items:
                    return items
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Fallback to token_creation_info
        url = f"{_BASE_URL}/defi/token_creation_info?chain={c}&limit={limit}&offset={offset}"
        raw = _safe_get(url, self.headers)
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
        return data.get("data", {}).get("items", []) if isinstance(data.get("data"), dict) else []

    def token_overview(self, token_address: str, chain: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get detailed token overview including social links, creator info."""
        c = chain or self.chain
        url = f"{_BASE_URL}/defi/token_overview?address={token_address}&chain={c}"
        raw = _safe_get(url, self.headers)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        return data.get("data", {})

    def token_metadata(self, token_address: str, chain: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get basic token metadata."""
        c = chain or self.chain
        url = f"{_BASE_URL}/defi/token_metadata?address={token_address}&chain={c}"
        raw = _safe_get(url, self.headers)
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        return data.get("data", {})

    @staticmethod
    def normalize_token(item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Birdeye token_creation item to internal format."""
        return {
            "mint": item.get("address"),
            "name": item.get("name"),
            "ticker": item.get("symbol"),
            "decimals": item.get("decimals"),
            "creator": item.get("creator"),
            "created_at": item.get("created_at"),
            "chain": item.get("chain"),
            "logo_uri": item.get("logo_uri"),
            "description": item.get("description", ""),
            "website": item.get("website", ""),
            "telegram": item.get("telegram", ""),
            "twitter": item.get("twitter", ""),
            "discord": item.get("discord", ""),
            "initial_liquidity_usd": float(item.get("initial_liquidity", 0) or 0),
            "initial_market_cap_usd": float(item.get("initial_market_cap", 0) or 0),
        }

    @staticmethod
    def normalize_overview(data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Birdeye token_overview response."""
        return {
            "mint": data.get("address"),
            "name": data.get("name"),
            "ticker": data.get("symbol"),
            "creator": data.get("creator"),
            "created_at": data.get("created_at"),
            "social_links": {
                "website": data.get("website", ""),
                "telegram": data.get("telegram", ""),
                "twitter": data.get("twitter", ""),
                "discord": data.get("discord", ""),
            },
            "extensions": data.get("extensions", {}),
            "volume_24h": float(data.get("volume_24h", 0) or 0),
            "price_usd": float(data.get("price", 0) or 0),
            "market_cap": float(data.get("market_cap", 0) or 0),
            "liquidity": float(data.get("liquidity", 0) or 0),
            "holder_count": int(data.get("holder_count", 0) or 0),
        }