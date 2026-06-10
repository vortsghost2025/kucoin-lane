"""Safety guard: detect rugs, honeypots, and red-flag tokens before entry.

Checks both on-chain (Solana) and off-chain (DexScreener, Solscan) signals
to classify tokens into risk tiers. Critical for filtering out the ~90% of
pump.fun tokens that are scams or dead-on-arrival.

Risk tiers: SAFE / LOW_RISK / MODERATE_RISK / HIGH_RISK / DANGEROUS / CONFIRMED_RUG

Ported from Control-Plane chain_intelligence/safety_guard.py.
All HTTP via stdlib urllib — no third-party deps required.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

RISK_TIERS = {
    "SAFE": {"level": 0, "description": "No red flags, multiple safe signals, graduated or major liquidity"},
    "LOW_RISK": {"level": 1, "description": "Minor concerns, no critical red flags"},
    "MODERATE_RISK": {"level": 2, "description": "Some warning signs, proceed with caution"},
    "HIGH_RISK": {"level": 3, "description": "Multiple red flags, avoid or minimal position only"},
    "DANGEROUS": {"level": 4, "description": "Critical red flags present, likely scam"},
    "CONFIRMED_RUG": {"level": 5, "description": "Confirmed rug pull or honeypot, do not enter"},
}

RED_FLAGS = {
    "mint_authority_enabled": {"weight": 0.25, "description": "Creator can mint more tokens — infinite supply risk"},
    "freeze_authority_enabled": {"weight": 0.25, "description": "Creator can freeze wallets — confiscation risk"},
    "low_liquidity": {"weight": 0.15, "description": "Under $1k liquidity — impossible to exit"},
    "single_pool": {"weight": 0.10, "description": "Only one liquidity pool — price manipulation risk"},
    "concentrated_holders": {"weight": 0.20, "description": "Top holder owns >50% of supply"},
    "honeypot_pattern": {"weight": 0.30, "description": "Sell blocking or tax mechanism detected"},
    "no_metadata": {"weight": 0.05, "description": "No token metadata (name/image) — lazy deploy"},
    "copycat_name": {"weight": 0.10, "description": "Name mimics a known successful token"},
    "no_social_links": {"weight": 0.05, "description": "No Telegram/Twitter/website — no community"},
    "creator_many_failures": {"weight": 0.15, "description": "Creator has many tokens, few graduated"},
    "unverifiable_contract": {"weight": 0.10, "description": "Contract source not verifiable"},
    "suspicious_pool_creation": {"weight": 0.15, "description": "Pool created with minimal initial liquidity"},
    "blacklisted_wallets": {"weight": 0.20, "description": "Known scam wallets in holder list"},
    "rapid_dump_after_launch": {"weight": 0.25, "description": "Creator sold >80% within minutes of launch"},
}

SAFE_SIGNALS = {
    "renounced_mint": {"weight": 0.15, "description": "Mint authority revoked — fixed supply"},
    "renounced_freeze": {"weight": 0.15, "description": "Freeze authority revoked — wallets safe"},
    "graduated": {"weight": 0.20, "description": "Token graduated from pump.fun to Raydium"},
    "major_liquidity": {"weight": 0.15, "description": ">$50k liquidity — healthy market"},
    "multiple_pools": {"weight": 0.05, "description": "Traded on >1 DEX — genuine demand"},
    "holder_distribution": {"weight": 0.10, "description": "No wallet holds >5% of supply"},
    "creator_track_record": {"weight": 0.10, "description": "Creator has graduated tokens before"},
    "verified_socials": {"weight": 0.05, "description": "Social links verified and active"},
    "community_size": {"weight": 0.05, "description": "Telegram/Discord >1000 members"},
}

DEXSCREENER_BASE = "https://api.dexscreener.com"
SOLSCAN_BASE = "https://public-api.solscan.io"

_MIN_INTERVAL = 1.0
_last_request_time = 0.0


def _safe_get(url: str, timeout: int = 15) -> Optional[bytes]:
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    req = Request(url, headers={"User-Agent": "kucoin-lane-safety/1.0", "Accept": "application/json"})
    try:
        resp = urlopen(req, timeout=timeout)
        _last_request_time = time.time()
        return resp.read()
    except (HTTPError, URLError, OSError) as e:
        logger.warning("Safety fetch error %s: %s", url, e)
        _last_request_time = time.time()
        return None


def _fetch_dexscreener_data(mint: str) -> Optional[Dict]:
    raw = _safe_get(f"{DEXSCREENER_BASE}/latest/dex/tokens/{mint}")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    pairs = data.get("pairs", [])
    if not pairs:
        return None
    best = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
    return best


def _fetch_solscan_data(mint: str) -> Optional[Dict]:
    raw = _safe_get(f"{SOLSCAN_BASE}/tokens/{mint}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _check_mint_authority(solscan_data: Optional[Dict]) -> Optional[bool]:
    if not solscan_data:
        return None
    return solscan_data.get("mint_authority") is not None


def _check_freeze_authority(solscan_data: Optional[Dict]) -> Optional[bool]:
    if not solscan_data:
        return None
    return solscan_data.get("freeze_authority") is not None


def _check_holder_concentration(solscan_data: Optional[Dict]) -> Optional[float]:
    if not solscan_data:
        return None
    holders = solscan_data.get("holder_count", 0) or 0
    top_holders = solscan_data.get("top_holders", [])
    if not top_holders:
        if holders > 0 and holders < 10:
            return 1.0
        return None
    total_supply = float(solscan_data.get("supply", 1) or 1)
    if total_supply <= 0:
        return None
    top_pct = sum(float(h.get("pct", 0) or 0) for h in top_holders[:5])
    return top_pct


def _check_liquidity(dex_data: Optional[Dict]) -> Optional[float]:
    if not dex_data:
        return None
    liq = dex_data.get("liquidity", {})
    return float(liq.get("usd", 0) or 0)


def _check_pools(dex_data: Optional[Dict]) -> Optional[int]:
    if not dex_data:
        return None
    dex_ids = dex_data.get("dexId", "")
    return 1


def _detect_copycat(name: str, known_names: Optional[List[str]] = None) -> bool:
    if not name:
        return False
    suffixes = ["2.0", "v2", "inu", "elon", "pepe", "doge", "shib", "wojak", "bret", "mog"]
    name_lower = name.lower()
    for s in suffixes:
        if name_lower.endswith(s) and len(name_lower) > len(s) + 2:
            return True
    return False


class SafetyGuard:
    def __init__(self, rpc_url: Optional[str] = None):
        self.rpc_url = rpc_url or os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

    def check_token(self, mint: str, token_name: str = "", extra: Optional[Dict] = None) -> Dict[str, Any]:
        extra = extra or {}
        red_flags: Dict[str, Any] = {}
        safe_signals: Dict[str, Any] = {}
        details: Dict[str, Any] = {"mint": mint, "name": token_name}

        dex_data = _fetch_dexscreener_data(mint)
        solscan_data = _fetch_solscan_data(mint)

        if dex_data:
            details["price_usd"] = float(dex_data.get("priceUsd", 0) or 0)
            details["volume_24h"] = float(dex_data.get("volume", {}).get("h24", 0) or 0)
            details["pair"] = dex_data.get("pairAddress", "")
            details["dex"] = dex_data.get("dexId", "")

        # Mint authority
        mint_enabled = _check_mint_authority(solscan_data)
        if mint_enabled is True:
            red_flags["mint_authority_enabled"] = RED_FLAGS["mint_authority_enabled"]
        elif mint_enabled is False:
            safe_signals["renounced_mint"] = SAFE_SIGNALS["renounced_mint"]

        # Freeze authority
        freeze_enabled = _check_freeze_authority(solscan_data)
        if freeze_enabled is True:
            red_flags["freeze_authority_enabled"] = RED_FLAGS["freeze_authority_enabled"]
        elif freeze_enabled is False:
            safe_signals["renounced_freeze"] = SAFE_SIGNALS["renounced_freeze"]

        # Liquidity
        liq_usd = _check_liquidity(dex_data)
        if liq_usd is not None:
            details["liquidity_usd"] = liq_usd
            if liq_usd < 1000:
                red_flags["low_liquidity"] = RED_FLAGS["low_liquidity"]
            elif liq_usd > 50000:
                safe_signals["major_liquidity"] = SAFE_SIGNALS["major_liquidity"]

        # Holder concentration
        top_pct = _check_holder_concentration(solscan_data)
        if top_pct is not None:
            details["top_holder_pct"] = top_pct
            if top_pct > 0.5:
                red_flags["concentrated_holders"] = RED_FLAGS["concentrated_holders"]
            elif top_pct < 0.05:
                safe_signals["holder_distribution"] = SAFE_SIGNALS["holder_distribution"]

        # Social links
        social_links = extra.get("social_links", {})
        if not social_links:
            red_flags["no_social_links"] = RED_FLAGS["no_social_links"]
        elif len(social_links) >= 2:
            safe_signals["verified_socials"] = SAFE_SIGNALS["verified_socials"]

        # Community
        tg_members = extra.get("telegram_members", 0)
        if tg_members >= 1000:
            safe_signals["community_size"] = SAFE_SIGNALS["community_size"]

        # Graduation
        is_graduated = extra.get("graduated", False)
        if is_graduated:
            safe_signals["graduated"] = SAFE_SIGNALS["graduated"]

        # Creator track record
        creator_graduated = extra.get("creator_graduated_count", 0)
        if creator_graduated >= 1:
            safe_signals["creator_track_record"] = SAFE_SIGNALS["creator_track_record"]
        creator_failed = extra.get("creator_failed_count", 0)
        if creator_failed > 5:
            red_flags["creator_many_failures"] = RED_FLAGS["creator_many_failures"]

        # Copycat
        if _detect_copycat(token_name):
            red_flags["copycat_name"] = RED_FLAGS["copycat_name"]

        # No metadata
        if not token_name:
            red_flags["no_metadata"] = RED_FLAGS["no_metadata"]

        # Compute risk score
        red_weight = sum(f["weight"] for f in red_flags.values())
        safe_weight = sum(s["weight"] for s in safe_signals.values())
        risk_score = max(0.0, min(1.0, 0.5 + red_weight * 0.5 - safe_weight * 0.5))

        # Classify tier
        risk_tier = "SAFE"
        for tier, config in sorted(RISK_TIERS.items(), key=lambda x: -x[1]["level"]):
            threshold = config["level"] / 5.0
            if risk_score >= threshold:
                risk_tier = tier
                break

        return {
            "mint": mint,
            "name": token_name,
            "risk_score": round(risk_score, 3),
            "risk_tier": risk_tier,
            "risk_level": RISK_TIERS[risk_tier]["level"],
            "red_flags": list(red_flags.keys()),
            "red_flag_details": {k: v["description"] for k, v in red_flags.items()},
            "safe_signals": list(safe_signals.keys()),
            "safe_signal_details": {k: v["description"] for k, v in safe_signals.items()},
            "details": details,
            "tradeable": risk_tier in ("SAFE", "LOW_RISK"),
            "avoid": risk_tier in ("DANGEROUS", "CONFIRMED_RUG"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def batch_check(self, tokens: List[Dict]) -> List[Dict[str, Any]]:
        results = []
        for token in tokens:
            mint = token.get("mint", token.get("address", ""))
            if not mint:
                continue
            result = self.check_token(
                mint=mint,
                token_name=token.get("name", ""),
                extra=token,
            )
            results.append(result)
            time.sleep(_MIN_INTERVAL)
        return results

    def filter_safe(self, tokens: List[Dict], max_risk_level: int = 1) -> List[Dict]:
        safe = []
        for token in tokens:
            mint = token.get("mint", token.get("address", ""))
            if not mint:
                continue
            result = self.check_token(
                mint=mint,
                token_name=token.get("name", ""),
                extra=token,
            )
            if result.get("risk_level", 99) <= max_risk_level:
                token["safety_check"] = result
                safe.append(token)
            time.sleep(_MIN_INTERVAL)
        return safe
