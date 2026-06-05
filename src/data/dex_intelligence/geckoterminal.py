import logging
import time
import threading
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.geckoterminal.com/api/v2"
_MIN_INTERVAL = 1.5
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
    req = Request(
        url,
        headers={
            "User-Agent": "cp-dex-intelligence/1.0",
            "Accept": "application/json",
        },
    )
    resp = urlopen(req, timeout=timeout)
    return resp.read()


def _safe_get(url: str, retries: int = 3, timeout: int = 15) -> Optional[bytes]:
    for attempt in range(retries):
        try:
            return _rate_limited_get(url, timeout=timeout)
        except HTTPError as e:
            if e.code in (429, 418):
                time.sleep((attempt + 1) * 3)
                continue
            logger.warning("GeckoTerminal HTTP %s for %s", e.code, url)
            return None
        except (URLError, OSError) as e:
            logger.warning("GeckoTerminal network error: %s", e)
            time.sleep((attempt + 1) * 1)
    return None


class GeckoTerminalProvider:
    def __init__(self, chain: str = "solana"):
        self.chain = chain

    def trending_pools(self, chain: Optional[str] = None, page: int = 1) -> List[Dict[str, Any]]:
        network = chain or self.chain
        url = f"{_BASE_URL}/networks/{network}/trending_pools?page={page}"
        raw = _safe_get(url)
        if not raw:
            return []
        data = json.loads(raw)
        return data.get("data", [])

    def new_pools(self, chain: Optional[str] = None, page: int = 1) -> List[Dict[str, Any]]:
        network = chain or self.chain
        url = f"{_BASE_URL}/networks/{network}/new_pools?page={page}"
        raw = _safe_get(url)
        if not raw:
            return []
        data = json.loads(raw)
        return data.get("data", [])

    def pool_info(self, chain: str, pool_address: str) -> Optional[Dict[str, Any]]:
        url = f"{_BASE_URL}/networks/{chain}/pools/{pool_address}"
        raw = _safe_get(url)
        if not raw:
            return None
        data = json.loads(raw)
        return data.get("data", {})

    def token_info(self, chain: str, token_address: str) -> Optional[Dict[str, Any]]:
        url = f"{_BASE_URL}/networks/{chain}/tokens/{token_address}"
        raw = _safe_get(url)
        if not raw:
            return None
        data = json.loads(raw)
        return data.get("data", {})

    @staticmethod
    def normalize_pool(pool: Dict[str, Any]) -> Dict[str, Any]:
        attr = pool.get("attributes", {})
        rel = pool.get("relationships", {})
        txns_h24 = attr.get("transactions", {}).get("h24", {})
        return {
            "pool_address": attr.get("address"),
            "name": attr.get("name"),
            "chain": pool.get("attributes", {}).get("network_id", ""),
            "volume_usd_24h": float(attr.get("volume_usd", {}).get("h24", 0) or 0) if isinstance(attr.get("volume_usd"), dict) else float(attr.get("volume_usd", 0) or 0),
            "price_change_24h": float(attr.get("price_change_percentage", {}).get("h24", 0) or 0) if isinstance(attr.get("price_change_percentage"), dict) else 0.0,
            "buys_24h": int(txns_h24.get("buys", 0) or 0),
            "sells_24h": int(txns_h24.get("sells", 0) or 0),
            "buyers_24h": int(txns_h24.get("buyers", 0) or 0),
            "sellers_24h": int(txns_h24.get("sellers", 0) or 0),
            "reserve_in_usd": float(attr.get("reserve_in_usd", 0) or 0),
            "pool_created_at": attr.get("pool_created_at"),
            "token_base": rel.get("base_token", {}).get("data", {}).get("id", ""),
            "token_quote": rel.get("quote_token", {}).get("data", {}).get("id", ""),
        }
