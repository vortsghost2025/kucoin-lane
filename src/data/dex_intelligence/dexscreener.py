import logging
import time
import threading
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import quote
import json

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.dexscreener.com"
_MIN_INTERVAL = 1.0
_last_call_ts = 0.0
_lock = threading.Lock()


def _rate_limited_get(url: str, timeout: int = 15) -> bytes:
    global _last_call_ts
    with _lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.monotonic()
    req = Request(url, headers={"User-Agent": "cp-dex-intelligence/1.0"})
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
            logger.warning("DexScreener HTTP %s for %s", e.code, url)
            return None
        except (URLError, OSError) as e:
            logger.warning("DexScreener network error: %s", e)
            time.sleep((attempt + 1) * 1)
    return None


class DexScreenerProvider:
    def __init__(self, chain: str = "solana"):
        self.chain = chain

    def search(self, query: str) -> List[Dict[str, Any]]:
        url = f"{_BASE_URL}/latest/dex/search?q={quote(query)}"
        raw = _safe_get(url)
        if not raw:
            return []
        data = json.loads(raw)
        return data.get("pairs", [])

    def get_token(self, chain_id: str, token_address: str) -> Optional[Dict[str, Any]]:
        url = f"{_BASE_URL}/latest/dex/tokens/{token_address}"
        raw = _safe_get(url)
        if not raw:
            return None
        data = json.loads(raw)
        pairs = data.get("pairs", [])
        chain_pairs = [p for p in pairs if p.get("chainId") == chain_id]
        return chain_pairs[0] if chain_pairs else (pairs[0] if pairs else None)

    def get_pair(self, chain_id: str, pair_address: str) -> Optional[Dict[str, Any]]:
        url = f"{_BASE_URL}/latest/dex/pairs/{chain_id}/{pair_address}"
        raw = _safe_get(url)
        if not raw:
            return None
        data = json.loads(raw)
        pairs = data.get("pairs", [])
        return pairs[0] if pairs else None

    def trending_tokens(self, chain_id: Optional[str] = None) -> List[Dict[str, Any]]:
        url = f"{_BASE_URL}/token-profiles/latest/v1"
        if chain_id:
            url += f"?chainId={chain_id}"
        raw = _safe_get(url)
        if not raw:
            return []
        return json.loads(raw)

    def latest_token_profiles(self, chain_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.trending_tokens(chain_id)

    def new_pairs(self, chain_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get newly created pairs (uses token-profiles/latest which shows recently added tokens)."""
        profiles = self.trending_tokens(chain_id)
        if not profiles:
            return []
        results = []
        for profile in profiles[:limit]:
            mint = profile.get("tokenAddress", "")
            if not mint:
                continue
            links = profile.get("links", [])
            social = {}
            for link in links:
                ltype = link.get("type", "").lower()
                if ltype in ("twitter", "telegram", "website", "discord"):
                    social[ltype] = link.get("url", "")
            # Extract ticker from description or use mint prefix
            desc = profile.get("description", "")
            ticker = ""
            if desc:
                # Try to extract a reasonable ticker from description
                words = desc.split()
                for w in words:
                    if w.isupper() and 2 <= len(w) <= 10 and w.isalpha():
                        ticker = w
                        break
            if not ticker:
                ticker = mint[:8]
            results.append({
                "mint": mint,
                "name": desc[:100] if desc else "",
                "ticker": ticker,
                "description": desc,
                "social_links": social,
                "links_raw": links,
                "dexscreener_url": profile.get("url", ""),
                "icon": profile.get("icon", ""),
                "cto": profile.get("cto", False),
                "updated_at": profile.get("updatedAt", ""),
            })
        return results

    @staticmethod
    def normalize_pair(pair: Dict[str, Any]) -> Dict[str, Any]:
        bt = pair.get("baseToken", {})
        qt = pair.get("quoteToken", {})
        vol = pair.get("volume", {})
        liq = pair.get("liquidity", {})
        txns = pair.get("txns", {})
        h24 = txns.get("h24", {})
        h6 = txns.get("h6", {})
        h1 = txns.get("h1", {})
        price_change = pair.get("priceChange", {})
        return {
            "pair_address": pair.get("pairAddress"),
            "chain": pair.get("chainId"),
            "dex": pair.get("dexId"),
            "url": pair.get("url"),
            "base_token": {
                "address": bt.get("address"),
                "symbol": bt.get("symbol"),
                "name": bt.get("name"),
            },
            "quote_token": {
                "address": qt.get("address"),
                "symbol": qt.get("symbol"),
                "name": qt.get("name"),
            },
            "price_usd": float(pair.get("priceUsd", 0) or 0),
            "price_native": float(pair.get("priceNative", 0) or 0),
            "volume_24h": float(vol.get("h24", 0) or 0),
            "volume_6h": float(vol.get("h6", 0) or 0),
            "volume_1h": float(vol.get("h1", 0) or 0),
            "liquidity_usd": float(liq.get("usd", 0) or 0),
            "fdv": float(pair.get("fdv", 0) or 0),
            "market_cap": float(pair.get("marketCap", 0) or 0),
            "buys_24h": int(h24.get("buys", 0) or 0),
            "sells_24h": int(h24.get("sells", 0) or 0),
            "buys_1h": int(h1.get("buys", 0) or 0),
            "sells_1h": int(h1.get("sells", 0) or 0),
            "price_change_24h": float(price_change.get("h24", 0) or 0),
            "price_change_6h": float(price_change.get("h6", 0) or 0),
            "price_change_1h": float(price_change.get("h1", 0) or 0),
            "pair_created_at": pair.get("pairCreatedAt"),
        }
