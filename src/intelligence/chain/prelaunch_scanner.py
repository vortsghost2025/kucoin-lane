"""Pre-launch intelligence: discover token communities before they launch.

PumpFun token creators build communities on Telegram, X/Twitter, Discord, and
other platforms BEFORE hitting the bonding curve. This module:

1. Scrapes PumpFun token metadata for social links (TG group, X handle, website)
2. Monitors "Callouts" section for upcoming launches
3. Discovers launch coordination communities
4. Extracts creator profiles for reputation scoring
5. Ranks pre-launch tokens by community momentum

The key insight: tokens with organized communities BEFORE launch have much
higher graduation rates than random launches. Finding these early is the
highest-alpha signal in the memecoin pipeline.

Ported from Control-Plane chain_intelligence/prelaunch_scanner.py.
All HTTP via stdlib urllib — no third-party deps required.
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from src.data.dex_intelligence.birdeye import BirdeyeProvider
from src.data.dex_intelligence.dexscreener import DexScreenerProvider
from src.intelligence.chain.helius_provider import HeliusProvider

logger = logging.getLogger(__name__)

PUMPFUN_BASE = "https://pump.fun"
PUMPFUN_API = "https://frontend-api.pump.fun"

LAUNCH_PLATFORM_KEYWORDS = [
    "rapidlaunch.io",
    "j7tracker.io",
    "launch",
    "presale",
    "fair launch",
    "stealth launch",
    "coming soon",
    "deploying",
    "launching",
]

COMMUNITY_PLATFORMS = {
    "telegram": re.compile(r"(?:t\.me|telegram\.me|tg:)/([a-zA-Z0-9_]+)", re.I),
    "twitter": re.compile(r"(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)", re.I),
    "discord": re.compile(r"discord\.(?:gg|com/invite)/([a-zA-Z0-9]+)", re.I),
    "website": re.compile(r"https?://([a-zA-Z0-9._-]+\.[a-z]{2,})", re.I),
}

CREATOR_REPUTATION_SIGNALS = {
    "has_profile": 0.1,
    "has_multiple_coins": 0.15,
    "has_graduated_coin": 0.3,
    "has_social_links": 0.1,
    "older_account": 0.1,
    "has_bio": 0.05,
}

PRE_LAUNCH_TIERS = {
    "HIGH_CONFIDENCE": {"min_score": 0.7, "description": "Organized community, experienced creator, multi-platform presence"},
    "PROMISING": {"min_score": 0.5, "description": "Some community building, social links present"},
    "SPECULATIVE": {"min_score": 0.3, "description": "Minimal signals, low community evidence"},
    "NOISE": {"min_score": 0.0, "description": "No community, no social links, likely spam"},
}

_MIN_INTERVAL = 0.5
_last_request_time = 0.0


def _safe_get(url: str, timeout: int = 15) -> Optional[bytes]:
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    req = Request(url, headers={"User-Agent": "kucoin-lane-prelaunch/1.0", "Accept": "application/json"})
    try:
        resp = urlopen(req, timeout=timeout)
        _last_request_time = time.time()
        return resp.read()
    except (HTTPError, URLError, OSError) as e:
        logger.warning("Pre-launch fetch error %s: %s", url, e)
        _last_request_time = time.time()
        return None


def extract_social_links(text: str) -> Dict[str, List[str]]:
    if not text:
        return {}
    links = {}
    for platform, pattern in COMMUNITY_PLATFORMS.items():
        matches = pattern.findall(text)
        if matches:
            links[platform] = list(set(matches))
    return links


def detect_launch_platforms(text: str) -> List[str]:
    if not text:
        return []
    text_lower = text.lower()
    return [kw for kw in LAUNCH_PLATFORM_KEYWORDS if kw in text_lower]


def compute_community_score(token_data: Dict) -> float:
    score = 0.0
    social_links = token_data.get("social_links", {})
    n_platforms = len(social_links)
    if n_platforms >= 3:
        score += 0.3
    elif n_platforms >= 2:
        score += 0.2
    elif n_platforms >= 1:
        score += 0.1

    tg_members = token_data.get("telegram_members", 0)
    if tg_members >= 5000:
        score += 0.25
    elif tg_members >= 1000:
        score += 0.2
    elif tg_members >= 200:
        score += 0.15
    elif tg_members >= 50:
        score += 0.1

    description = token_data.get("description", "") or ""
    launch_platforms = detect_launch_platforms(description)
    if launch_platforms:
        score += 0.1

    creator_score = token_data.get("creator_reputation", 0.0)
    score += creator_score * 0.2

    has_description = len(description) > 20
    if has_description:
        score += 0.05

    has_name = bool(token_data.get("name"))
    has_ticker = bool(token_data.get("ticker"))
    if has_name and has_ticker:
        score += 0.05

    return min(score, 1.0)


def classify_pre_launch(score: float) -> str:
    for tier, config in sorted(PRE_LAUNCH_TIERS.items(), key=lambda x: -x[1]["min_score"]):
        if score >= config["min_score"]:
            return tier
    return "NOISE"


class PreLaunchScanner:
    def __init__(self, rpc_url: Optional[str] = None):
        self.rpc_url = rpc_url or os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        self._creator_cache: Dict[str, Dict] = {}
        self.birdeye = BirdeyeProvider(chain="solana")
        self.dexscreener = DexScreenerProvider(chain="solana")
        self.helius = HeliusProvider()

    def scan_pumpfun_new(self, limit: int = 50) -> List[Dict[str, Any]]:
        raw = _safe_get(f"{PUMPFUN_API}/coins?offset=0&limit={limit}&sort=new")
        if not raw:
            raw = _safe_get(f"{PUMPFUN_API}/coins/latest?limit={limit}")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

        coins = data if isinstance(data, list) else data.get("coins", data.get("data", []))
        if not isinstance(coins, list):
            return []

        results = []
        for coin in coins[:limit]:
            enriched = self._enrich_token(coin)
            results.append(enriched)
        return results

    def scan_pumpfun_callouts(self, limit: int = 30) -> List[Dict[str, Any]]:
        raw = _safe_get(f"{PUMPFUN_API}/callouts?limit={limit}")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

        callouts = data if isinstance(data, list) else data.get("callouts", data.get("data", []))
        if not isinstance(callouts, list):
            return []

        results = []
        for callout in callouts[:limit]:
            coin = callout.get("coin", callout)
            enriched = self._enrich_token(coin)
            enriched["callout_type"] = callout.get("type", "unknown")
            results.append(enriched)
        return results

    def scan_birdeye_new(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Scan Birdeye for newly created tokens on Solana.
        
        Birdeye token_creation endpoint returns tokens with:
        - mint address, name, symbol, creator wallet
        - created_at timestamp
        - social links (website, telegram, twitter, discord)
        - initial liquidity, market cap
        
        This supplements pump.fun when their API is blocked.
        """
        items = self.birdeye.new_tokens(chain="solana", limit=limit)
        if not items:
            return []

        results = []
        for item in items[:limit]:
            normalized = BirdeyeProvider.normalize_token(item)
            enriched = self._enrich_token_from_birdeye(normalized)
            results.append(enriched)
        return results

    def scan_dexscreener_new(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Scan DexScreener for newly profiled tokens with social links.
        
        DexScreener token-profiles/latest returns tokens with:
        - mint address
        - description
        - social links (twitter, telegram, website)
        - icon/header images
        """
        items = self.dexscreener.new_pairs(chain_id="solana", limit=limit)
        if not items:
            return []
        
        results = []
        for item in items[:limit]:
            enriched = self._enrich_token_from_dexscreener(item)
            results.append(enriched)
        return results

    def _enrich_token_from_dexscreener(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich a DexScreener profile with community scoring."""
        mint = item.get("mint", "")
        description = item.get("description", "")
        social_links = item.get("social_links", {})
        
        # Extract ticker from name or use shortened mint
        name = item.get("name", "")
        ticker = name[:10] if name else mint[:8]
        
        launch_platforms = detect_launch_platforms(description)
        creator_rep = self._score_creator("", item)
        
        token_data = {
            "name": name,
            "ticker": ticker,
            "mint": mint,
            "description": description[:200],
            "creator": "",
            "market_cap_usd": 0,
            "created_at": 0,
            "social_links": social_links,
            "n_social_platforms": len(social_links),
            "launch_platforms": launch_platforms,
            "creator_reputation": creator_rep,
        }
        
        community_score = compute_community_score(token_data)
        token_data["community_score"] = round(community_score, 3)
        token_data["pre_launch_tier"] = classify_pre_launch(community_score)
        
        return token_data

    def resolve_creators(self, tokens: List[Dict[str, Any]], delay: float = 0.1) -> Dict[str, Optional[str]]:
        """Resolve creator wallets for tokens using Helius.
        
        Only resolves for tokens that don't already have a creator.
        Returns dict mapping mint -> creator wallet (or None).
        """
        mints_to_resolve = []
        for token in tokens:
            mint = token.get("mint", "")
            if mint and not token.get("creator"):
                mints_to_resolve.append(mint)
        
        if not mints_to_resolve:
            return {}
        
        logger.info(f"Resolving creators for {len(mints_to_resolve)} tokens via Helius...")
        creators = self.helius.get_creators_batch(mints_to_resolve, delay=delay)
        
        # Update tokens with resolved creators
        for token in tokens:
            mint = token.get("mint", "")
            if mint in creators and creators[mint]:
                token["creator"] = creators[mint]
        
        return creators

    def scan_all_sources(self, limit: int = 50, resolve_creators: bool = True) -> List[Dict[str, Any]]:
        """Scan all available sources (pump.fun + Birdeye) and merge results.
        
        Deduplicates by mint address, preferring richer data.
        """
        pumpfun = self.scan_pumpfun_new(limit=limit)
        birdeye = self.scan_birdeye_new(limit=limit)
        dexscreener = self.scan_dexscreener_new(limit=limit)
        
        # Merge by mint, preferring data with more fields
        by_mint: Dict[str, Dict] = {}
        for token in pumpfun + birdeye + dexscreener:
            mint = token.get("mint", "")
            if not mint:
                continue
            if mint not in by_mint or len(token) > len(by_mint[mint]):
                by_mint[mint] = token
            else:
                # Merge social links
                existing = by_mint[mint].get("social_links", {})
                new_links = token.get("social_links", {})
                for platform, handle in new_links.items():
                    if platform not in existing:
                        existing[platform] = handle
                by_mint[mint]["social_links"] = existing
        
        # Re-score merged tokens
        merged = list(by_mint.values())
        for token in merged:
            token["community_score"] = compute_community_score(token)
            token["pre_launch_tier"] = classify_pre_launch(token["community_score"])
        
        # Sort by community score descending
        merged.sort(key=lambda t: t.get("community_score", 0), reverse=True)
        
        # Resolve creators via Helius (if enabled)
        if resolve_creators:
            self.resolve_creators(merged)
        
        return merged[:limit]

    def get_token_social_links(self, mint: str) -> Dict[str, Any]:
        raw = _safe_get(f"{PUMPFUN_API}/coin/{mint}")
        if not raw:
            return {"mint": mint, "social_links": {}, "error": "fetch_failed"}
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {"mint": mint, "social_links": {}, "error": "parse_failed"}

        return self._enrich_token(data)

    def discover_launch_communities(self, tokens: List[Dict]) -> Dict[str, Any]:
        all_tg_groups = set()
        all_twitter = set()
        all_discord = set()
        launch_platform_counts: Dict[str, int] = {}

        for token in tokens:
            links = token.get("social_links", {})
            for tg in links.get("telegram", []):
                all_tg_groups.add(tg)
            for tw in links.get("twitter", []):
                all_twitter.add(tw)
            for dc in links.get("discord", []):
                all_discord.add(dc)
            for lp in token.get("launch_platforms", []):
                launch_platform_counts[lp] = launch_platform_counts.get(lp, 0) + 1

        high_confidence = [t for t in tokens if t.get("pre_launch_tier") == "HIGH_CONFIDENCE"]
        promising = [t for t in tokens if t.get("pre_launch_tier") == "PROMISING"]

        return {
            "scan_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tokens_scanned": len(tokens),
            "unique_tg_groups": len(all_tg_groups),
            "unique_twitter_accounts": len(all_twitter),
            "unique_discord_servers": len(all_discord),
            "tg_groups": sorted(all_tg_groups),
            "twitter_accounts": sorted(all_twitter),
            "discord_servers": sorted(all_discord),
            "launch_platforms": launch_platform_counts,
            "high_confidence_tokens": len(high_confidence),
            "promising_tokens": len(promising),
            "high_confidence_list": [
                {"name": t.get("name"), "ticker": t.get("ticker"), "score": t.get("community_score")}
                for t in high_confidence[:10]
            ],
            "recommended_monitoring": sorted(all_tg_groups)[:20],
        }

    def _enrich_token(self, coin: Dict) -> Dict[str, Any]:
        name = coin.get("name", "")
        ticker = coin.get("ticker", coin.get("symbol", ""))
        description = coin.get("description", "") or ""
        mint = coin.get("mint", coin.get("address", ""))
        creator = coin.get("creator", coin.get("deployer", ""))

        social_text = " ".join(filter(None, [
            description,
            coin.get("website", ""),
            coin.get("telegram", ""),
            coin.get("twitter", ""),
        ]))
        social_links = extract_social_links(social_text)

        if coin.get("telegram") and "telegram" not in social_links:
            tg_val = coin["telegram"]
            if isinstance(tg_val, str):
                tg_matches = COMMUNITY_PLATFORMS["telegram"].findall(tg_val)
                if tg_matches:
                    social_links.setdefault("telegram", []).extend(tg_matches)
                elif not tg_val.startswith("http"):
                    social_links.setdefault("telegram", []).append(tg_val)

        if coin.get("twitter") and "twitter" not in social_links:
            tw_val = coin["twitter"]
            if isinstance(tw_val, str):
                tw_matches = COMMUNITY_PLATFORMS["twitter"].findall(tw_val)
                if tw_matches:
                    social_links.setdefault("twitter", []).extend(tw_matches)
                elif not tw_val.startswith("http"):
                    social_links.setdefault("twitter", []).append(tw_val)

        launch_platforms = detect_launch_platforms(description)

        creator_rep = self._score_creator(creator, coin)

        market_cap = coin.get("market_cap", coin.get("usd_market_cap", 0)) or 0
        created_at = coin.get("created_at", coin.get("pairCreatedAt", 0))

        token_data = {
            "name": name,
            "ticker": ticker,
            "mint": mint,
            "description": description[:200],
            "creator": creator,
            "market_cap_usd": market_cap,
            "created_at": created_at,
            "social_links": social_links,
            "n_social_platforms": len(social_links),
            "launch_platforms": launch_platforms,
            "creator_reputation": creator_rep,
        }

        community_score = compute_community_score(token_data)
        token_data["community_score"] = round(community_score, 3)
        token_data["pre_launch_tier"] = classify_pre_launch(community_score)

        return token_data

    def _enrich_token_from_birdeye(self, normalized: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich a Birdeye-normalized token with community scoring."""
        mint = normalized.get("mint", "")
        creator = normalized.get("creator", "")
        description = normalized.get("description", "")
        
        social_links = {}
        for platform in ("website", "telegram", "twitter", "discord"):
            val = normalized.get(platform, "")
            if val:
                social_links[platform] = val
        
        # Try to get richer overview from Birdeye if we have API key
        if self.birdeye.api_key and mint:
            try:
                overview = self.birdeye.token_overview(mint)
                if overview:
                    ov_norm = BirdeyeProvider.normalize_overview(overview)
                    for platform, handle in ov_norm.get("social_links", {}).items():
                        if handle and platform not in social_links:
                            social_links[platform] = handle
            except Exception as e:
                logger.debug(f"Birdeye overview fetch failed for {mint}: {e}")
        
        launch_platforms = detect_launch_platforms(description)
        creator_rep = self._score_creator(creator, normalized)
        
        token_data = {
            "name": normalized.get("name", ""),
            "ticker": normalized.get("ticker", ""),
            "mint": mint,
            "description": description[:200],
            "creator": creator,
            "market_cap_usd": normalized.get("initial_market_cap_usd", 0),
            "created_at": normalized.get("created_at", 0),
            "social_links": social_links,
            "n_social_platforms": len(social_links),
            "launch_platforms": launch_platforms,
            "creator_reputation": creator_rep,
        }
        
        community_score = compute_community_score(token_data)
        token_data["community_score"] = round(community_score, 3)
        token_data["pre_launch_tier"] = classify_pre_launch(community_score)
        
        return token_data

    def _score_creator(self, creator: str, coin: Dict) -> float:
        if not creator:
            return 0.0
        if creator in self._creator_cache:
            return self._creator_cache[creator].get("score", 0.0)

        score = 0.0
        if coin.get("creator"):
            score += CREATOR_REPUTATION_SIGNALS["has_profile"]
        if coin.get("creator_bio") or coin.get("creator_name"):
            score += CREATOR_REPUTATION_SIGNALS["has_bio"]

        self._creator_cache[creator] = {"score": score}
        return score


KNOWN_LAUNCH_COMMUNITIES = {
    "tg_channels": [
        "pump_fun",
        "pumpfunportal",
        "pumpfunalerts",
        "solana_memecoin",
        "solana_gems",
        "dex_signals",
        "pumpcalls",
        "sol_degen",
        "memecoin_calls",
        "pump_fun_signals",
        "solanaalpha",
        "degen_callssol",
        "pumpfunsniper",
        "solgemalerts",
        "memecoinsolana",
        "pumpsolana",
        "cryptosignals_org",
        "solana_early",
        "pumpfun_early",
        "degens_tradings",
    ],
    "x_accounts": [
        "pumpdotfun",
        "solabscan",
        "dexscreener",
        "birdeye_geo",
        "gmgn_ai",
    ],
    "launch_platforms": [
        "rapidlaunch.io",
        "j7tracker.io",
        "pump.fun",
        "letsbonk.fun",
        "monke.lol",
        "memeos.fun",
    ],
    "discord_servers": [
        "pumpfun",
        "solana-ecosystem",
        "raydium",
        "jupiter-exchange",
    ],
}

MONITORING_RECOMMENDATIONS = {
    "high_value_tg_patterns": [
        "Token name + 'army'/'community'/'club'",
        "Pre-sale announcements with specific dates",
        "Dev wallets posting progress updates",
        "Coin creation countdown channels",
        "KOL call-out channels before pump.fun listing",
    ],
    "x_monitoring": [
        "Accounts that frequently announce pump.fun launches",
        "Hashtags: #pumpfun #solana #memecoin #launch",
        "Quote tweets of pump.fun coin announcements",
        "Spaces discussing upcoming launches",
    ],
    "on_chain_signals": [
        "Token metadata uploaded before bonding curve starts",
        "Creator wallet funded from known launch syndicates",
        "Multiple tokens from same creator (serial launcher)",
        "Social metadata URI uploaded (Metaplex)",
    ],
}
