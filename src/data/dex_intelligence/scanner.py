import json
import logging
import time
from typing import Any, Dict, List, Optional

from .dexscreener import DexScreenerProvider
from .geckoterminal import GeckoTerminalProvider
from .pumpfun import PumpFunTracker
from .phantom import PhantomLauncherScanner
from .signals import DexSignalScorer

logger = logging.getLogger(__name__)


class DexScanner:
    def __init__(
        self,
        chains: Optional[List[str]] = None,
        rpc_url: Optional[str] = None,
    ):
        self.chains = chains or ["solana"]
        self.ds = DexScreenerProvider()
        self.gt = GeckoTerminalProvider()
        self.pf = PumpFunTracker(rpc_url=rpc_url) if rpc_url else None
        self.phantom = PhantomLauncherScanner()
        self.scorer = DexSignalScorer()

    def scan_trending(self, chain: Optional[str] = None) -> List[Dict[str, Any]]:
        chain = chain or self.chains[0]
        results = []
        try:
            profiles = self.ds.trending_tokens(chain_id=chain)
            for profile in profiles[:30]:
                token_addr = profile.get("tokenAddress")
                if not token_addr:
                    continue
                pair_data = self.ds.get_token(chain, token_addr)
                if pair_data:
                    results.append(DexScreenerProvider.normalize_pair(pair_data))
        except Exception as e:
            logger.warning("DexScreener trending scan failed: %s", e)
        return results

    def scan_new_pools(self, chain: Optional[str] = None) -> List[Dict[str, Any]]:
        chain = chain or self.chains[0]
        results = []
        try:
            pools = self.gt.new_pools(chain=chain)
            for pool in pools[:20]:
                results.append(GeckoTerminalProvider.normalize_pool(pool))
        except Exception as e:
            logger.warning("GeckoTerminal new pools scan failed: %s", e)
        return results

    def scan_search(self, query: str) -> List[Dict[str, Any]]:
        results = []
        try:
            pairs = self.ds.search(query)
            for pair in pairs[:20]:
                results.append(DexScreenerProvider.normalize_pair(pair))
        except Exception as e:
            logger.warning("DexScreener search failed: %s", e)
        return results

    def scan_pumpfun(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.pf:
            logger.info("PumpFun tracker not initialized (no RPC URL)")
            return []
        try:
            return self.pf.get_recent_tokens(limit=limit)
        except Exception as e:
            logger.warning("PumpFun scan failed: %s", e)
            return []

    def scan_phantom(self) -> List[Dict[str, Any]]:
        """Scan for new token launches on Phantom.com."""
        try:
            return self.phantom.scan_new_launches()
        except Exception as e:
            logger.warning("Phantom scan failed: %s", e)
            return []

    def full_scan(self, chain: Optional[str] = None) -> Dict[str, Any]:
        chain = chain or self.chains[0]
        start = time.time()
        trending = self.scan_trending(chain)
        new_pools = self.scan_new_pools(chain)
        scored_trending = self.scorer.rank_pairs(trending, top_n=10)
        scored_new = []
        for pool in new_pools:
            name = pool.get("name", "UNKNOWN/UNKNOWN")
            parts = name.split("/")
            pool_scored = {
                "pair": name,
                "chain": pool.get("chain", chain),
                "composite_score": 0.0,
                "signal": "NEUTRAL",
                "cex_listing_likelihood": "LOW",
                "volume_usd_24h": pool.get("volume_usd_24h", 0),
                "buyers_24h": pool.get("buyers_24h", 0),
                "sellers_24h": pool.get("sellers_24h", 0),
                "pool_created_at": pool.get("pool_created_at"),
            }
            buy_ratio = 0.5
            total = pool.get("buys_24h", 0) + pool.get("sells_24h", 0)
            if total > 0:
                buy_ratio = pool.get("buys_24h", 0) / total
            vol = pool.get("volume_usd_24h", 0)
            if vol > 100000 and buy_ratio > 0.6:
                pool_scored["composite_score"] = 0.5
                pool_scored["signal"] = "BUY"
                pool_scored["cex_listing_likelihood"] = "MEDIUM"
            elif vol > 50000:
                pool_scored["composite_score"] = 0.3
                pool_scored["signal"] = "NEUTRAL"
            scored_new.append(pool_scored)
        pumpfun = self.scan_pumpfun(limit=10) if self.pf else []
        phantom = self.scan_phantom()
        elapsed = round(time.time() - start, 2)
        return {
            "scan_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "chain": chain,
            "elapsed_seconds": elapsed,
            "trending_count": len(trending),
            "new_pools_count": len(new_pools),
            "pumpfun_count": len(pumpfun),
            "phantom_count": len(phantom),
            "top_trending": scored_trending[:5],
            "top_new_pools": scored_new[:5],
            "pumpfun_graduation_candidates": [t for t in pumpfun if t.get("bonding_progress_pct", 0) >= 80],
            "phantom_recent_launches": phantom[:10],  # Include recent Phantom launches
            "summary": self._build_summary(scored_trending, scored_new, pumpfun, phantom),
        }

    @staticmethod
    def _build_summary(
        trending: List[Dict[str, Any]],
        new_pools: List[Dict[str, Any]],
        pumpfun: List[Dict[str, Any]],
        phantom: List[Dict[str, Any]] = None,
    ) -> str:
        if phantom is None:
            phantom = []
        strong_buys = [t for t in trending if t.get("signal") == "STRONG_BUY"]
        buys = [t for t in trending if t.get("signal") == "BUY"]
        graduated = [t for t in pumpfun if t.get("graduated")]
        near_grad = [t for t in pumpfun if t.get("bonding_progress_pct", 0) >= 80 and not t.get("graduated")]
        recent_launches = len(phantom)
        parts = []
        if strong_buys:
            parts.append(f"{len(strong_buys)} STRONG_BUY signals")
        if buys:
            parts.append(f"{len(buys)} BUY signals")
        if graduated:
            parts.append(f"{len(graduated)} PumpFun graduations")
        if near_grad:
            parts.append(f"{len(near_grad)} near-graduation")
        if recent_launches:
            parts.append(f"{recent_launches} Phantom launches")
        if not parts:
            return "No actionable signals detected"
        return "; ".join(parts)
