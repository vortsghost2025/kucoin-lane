import json
import logging
import time
import threading
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

PUMPFUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nmu78QPvXdhYmRRmmt1Mm9pUMP"
GRADUATION_THRESHOLD_SOL = 85.0
_DEFAULT_RPC = "https://api.mainnet-beta.solana.com"
_MIN_INTERVAL = 0.5
_last_call_ts = 0.0
_lock = threading.Lock()


def _rate_limited_post(url: str, body: bytes, timeout: int = 15) -> bytes:
    global _last_call_ts
    with _lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.monotonic()
    req = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "cp-dex-intelligence/1.0",
        },
    )
    resp = urlopen(req, timeout=timeout)
    return resp.read()


def _safe_post(url: str, body: bytes, retries: int = 3, timeout: int = 15) -> Optional[bytes]:
    for attempt in range(retries):
        try:
            return _rate_limited_post(url, body, timeout=timeout)
        except HTTPError as e:
            if e.code == 429:
                time.sleep((attempt + 1) * 3)
                continue
            logger.warning("PumpFun RPC HTTP %s", e.code)
            return None
        except (URLError, OSError) as e:
            logger.warning("PumpFun RPC error: %s", e)
            time.sleep((attempt + 1) * 1)
    return None


class PumpFunTracker:
    def __init__(self, rpc_url: str = _DEFAULT_RPC):
        self.rpc_url = rpc_url

    def get_signatures(self, limit: int = 20) -> List[Dict[str, Any]]:
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [PUMPFUN_PROGRAM_ID, {"limit": limit}],
        }).encode()
        raw = _safe_post(self.rpc_url, body)
        if not raw:
            return []
        data = json.loads(raw)
        return data.get("result", [])

    def get_recent_tokens(self, limit: int = 20) -> List[Dict[str, Any]]:
        sigs = self.get_signatures(limit=limit)
        tokens = []
        seen = set()
        for sig_info in sigs[:limit]:
            sig = sig_info.get("signature")
            if not sig or sig in seen:
                continue
            seen.add(sig)
            tx = self._get_transaction(sig)
            if not tx:
                continue
            token_info = self._parse_pumpfun_tx(tx)
            if token_info:
                tokens.append(token_info)
        return tokens

    def _get_transaction(self, signature: str) -> Optional[Dict[str, Any]]:
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
            ],
        }).encode()
        raw = _safe_post(self.rpc_url, body)
        if not raw:
            return None
        data = json.loads(raw)
        return data.get("result")

    def _parse_pumpfun_tx(self, tx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        meta = tx.get("meta", {})
        if not meta or meta.get("err"):
            return None
        inner = meta.get("innerInstructions", [])
        msg = tx.get("transaction", {}).get("message", {})
        accounts = msg.get("accountKeys", [])
        account_addresses = []
        for acc in accounts:
            if isinstance(acc, dict):
                account_addresses.append(acc.get("pubkey", ""))
            elif isinstance(acc, str):
                account_addresses.append(acc)
        log_messages = meta.get("logMessages", [])
        is_create = any("initialize" in str(m).lower() or "create" in str(m).lower() for m in log_messages)
        is_trade = any("buy" in str(m).lower() or "sell" in str(m).lower() for m in log_messages)
        bonding_progress = self._estimate_bonding_progress(log_messages)
        return {
            "signature": tx.get("transaction", {}).get("signatures", [""])[0],
            "slot": tx.get("slot"),
            "block_time": tx.get("blockTime"),
            "is_create": is_create,
            "is_trade": is_trade,
            "bonding_progress_pct": bonding_progress,
            "graduated": bonding_progress >= 100.0,
            "program_id": PUMPFUN_PROGRAM_ID,
            "account_count": len(account_addresses),
        }

    @staticmethod
    def _estimate_bonding_progress(log_messages: List[str]) -> float:
        for msg in log_messages:
            msg_str = str(msg).lower()
            if "bonding" in msg_str and "complete" in msg_str:
                return 100.0
            if "graduated" in msg_str or "raydium" in msg_str:
                return 100.0
        return 0.0

    def check_graduation_candidates(self, limit: int = 50) -> List[Dict[str, Any]]:
        tokens = self.get_recent_tokens(limit=limit)
        candidates = []
        for t in tokens:
            if t.get("bonding_progress_pct", 0) >= 80 and not t.get("graduated"):
                candidates.append(t)
            elif t.get("graduated"):
                candidates.append(t)
        return candidates
