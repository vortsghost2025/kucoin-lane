"""
Helius Provider - Creator Wallet Resolution
============================================
Fetches token creator wallets by analyzing mint creation transactions
via Helius RPC (getSignaturesForAddress + getTransaction).

Uses Helius enhanced RPC for reliable, fast on-chain data.
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

_MIN_INTERVAL = 0.1  # Helius free tier: 10 req/sec
_last_call_ts = 0.0
_lock = threading.Lock()


def _rate_limited_post(url: str, payload: Dict, timeout: int = 15) -> bytes:
    global _last_call_ts
    with _lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.monotonic()
    req = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "kucoin-lane-helius/1.0"},
        method="POST",
    )
    resp = urlopen(req, timeout=timeout)
    return resp.read()


def _safe_post(url: str, payload: Dict, retries: int = 3, timeout: int = 10) -> Optional[bytes]:
    for attempt in range(retries):
        try:
            return _rate_limited_post(url, payload, timeout=timeout)
        except HTTPError as e:
            if e.code in (429, 418):
                time.sleep((attempt + 1) * 0.5)
                continue
            logger.warning("Helius HTTP %s: %s", e.code, e.reason)
            return None
        except (URLError, OSError) as e:
            logger.warning("Helius network error: %s", e)
            time.sleep((attempt + 1) * 0.2)
    return None


class HeliusProvider:
    """Helius RPC provider for creator wallet resolution."""

    def __init__(self, api_key: Optional[str] = None, rpc_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("HELIUS_API_KEY")
        self.rpc_url = rpc_url or os.getenv("SOLANA_RPC_URL")
        if not self.rpc_url or "YOUR_HELIUS_API_KEY" in self.rpc_url:
            # Build from api_key if needed
            if self.api_key and "api-key=" not in self.rpc_url:
                self.rpc_url = f"https://mainnet.helius-rpc.com/?api-key={self.api_key}"
        logger.info(f"HeliusProvider initialized: {self.rpc_url[:50]}...")

    def get_mint_creator(self, mint: str) -> Optional[str]:
        """
        Get the creator wallet of a token by finding the mint creation transaction.
        
        Strategy:
        1. Get signatures for the mint address (newest first)
        2. Page backwards to find the oldest (creation) transaction
        3. Fee payer (accountKeys[0]) = creator
        
        For new tokens, creation tx is recent - only need a few pages.
        """
        if not self.rpc_url:
            return None

        # Step 1: Get signatures for mint address (newest first)
        # Use smaller limit, page back if needed
        sig_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [
                mint,
                {"limit": 50, "before": None}
            ]
        }
        
        all_signatures = []
        max_pages = 3  # Limit paging for speed
        
        for page in range(max_pages):
            raw = _safe_post(self.rpc_url, sig_payload)
            if not raw:
                break
            
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                break
            
            signatures = data.get("result", [])
            if not signatures:
                break
            
            all_signatures.extend(signatures)
            
            # If we got less than limit, we've reached the end (oldest)
            if len(signatures) < 50:
                break
            
            # Page back: use last signature as 'before' for next page
            sig_payload["params"][1]["before"] = signatures[-1]["signature"]
        
        if not all_signatures:
            logger.debug(f"No signatures found for mint {mint}")
            return None
        
        # Oldest signature = mint creation (last in the list)
        oldest_sig = all_signatures[-1]["signature"]
        
        # Step 2: Fetch the creation transaction
        tx_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "getTransaction",
            "params": [
                oldest_sig,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
            ]
        }
        
        raw = _safe_post(self.rpc_url, tx_payload)
        if not raw:
            return None
        
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        
        result = data.get("result")
        if not result:
            return None
        
        # Step 3: Extract fee payer (creator)
        # accountKeys[0] = fee payer = token creator
        message = result.get("transaction", {}).get("message", {})
        account_keys = message.get("accountKeys", [])
        
        if account_keys and isinstance(account_keys[0], dict):
            creator = account_keys[0].get("pubkey")
            if creator:
                logger.info(f"Resolved creator for {mint[:8]}...: {creator}")
                return creator
        
        return None

    def get_creators_batch(self, mints: List[str], delay: float = 0.1) -> Dict[str, Optional[str]]:
        """Resolve creators for multiple mints with rate limiting."""
        results = {}
        for mint in mints:
            creator = self.get_mint_creator(mint)
            results[mint] = creator
            if delay > 0:
                time.sleep(delay)
        return results


def get_creator_for_mint(mint: str, helius: Optional[HeliusProvider] = None) -> Optional[str]:
    """Convenience function for single mint creator lookup."""
    provider = helius or HeliusProvider()
    return provider.get_mint_creator(mint)