import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DexSignalScorer:
    def __init__(self):
        self.weights = {
            "volume_spike": 0.25,
            "tx_ratio": 0.15,
            "liquidity_depth": 0.15,
            "age_penalty": 0.10,
            "chain_multiplier": 0.10,
            "graduation_signal": 0.15,
            "volume_mcap_ratio": 0.10,
        }

    MIN_LIQUIDITY_USD = 50000.0
    MIN_VOLUME_USD = 10000.0
    MIN_MCAP_USD = 100000.0

    def score_pair(self, pair: Dict[str, Any]) -> Dict[str, Any]:
        scores = {}
        vol_24h = pair.get("volume_24h", 0)
        vol_6h = pair.get("volume_6h", 0)
        vol_1h = pair.get("volume_1h", 0)
        liq = pair.get("liquidity_usd", 0)
        mcap = pair.get("market_cap", 0) or pair.get("fdv", 0)
        buys_24h = pair.get("buys_24h", 0)
        sells_24h = pair.get("sells_24h", 0)
        total_txns = buys_24h + sells_24h
        buys_1h = pair.get("buys_1h", 0)
        sells_1h = pair.get("sells_1h", 0)
        total_1h = buys_1h + sells_1h
        created_at = pair.get("pair_created_at")

        if vol_24h > 0 and vol_6h > 0:
            ratio_6h_to_24h = (vol_6h / 4) / (vol_24h / 24) if vol_24h else 0
            scores["volume_spike"] = min(ratio_6h_to_24h / 3.0, 1.0) if ratio_6h_to_24h > 1 else 0.0
        else:
            scores["volume_spike"] = 0.0

        if total_txns > 0:
            buy_ratio = buys_24h / total_txns
            scores["tx_ratio"] = (buy_ratio - 0.5) * 2 if buy_ratio > 0.5 else 0.0
        else:
            scores["tx_ratio"] = 0.0

        if liq > 0 and vol_24h > 0:
            vol_liq = vol_24h / liq
            scores["liquidity_depth"] = min(vol_liq / 5.0, 1.0)
        else:
            scores["liquidity_depth"] = 0.0

        if mcap > 0 and vol_24h > 0:
            vol_mcap = vol_24h / mcap
            scores["volume_mcap_ratio"] = min(vol_mcap / 0.5, 1.0)
        else:
            scores["volume_mcap_ratio"] = 0.0

        if created_at:
            import time
            age_hours = (time.time() * 1000 - created_at) / 3_600_000
            if age_hours < 1:
                scores["age_penalty"] = -0.3
            elif age_hours < 6:
                scores["age_penalty"] = 0.1
            elif age_hours < 24:
                scores["age_penalty"] = 0.3
            elif age_hours < 168:
                scores["age_penalty"] = 0.5
            else:
                scores["age_penalty"] = 0.2
        else:
            scores["age_penalty"] = 0.0

        chain = pair.get("chain", "")
        chain_scores = {"solana": 0.8, "base": 0.6, "ethereum": 0.5, "arbitrum": 0.4, "bsc": 0.3}
        scores["chain_multiplier"] = chain_scores.get(chain, 0.2)

        graduated = pair.get("graduated", False)
        bonding = pair.get("bonding_progress_pct", 0)
        if graduated:
            scores["graduation_signal"] = 1.0
        elif bonding >= 80:
            scores["graduation_signal"] = 0.7
        else:
            scores["graduation_signal"] = 0.0

        composite = sum(scores.get(k, 0) * self.weights.get(k, 0) for k in self.weights)

        confidence_tier = "full"
        if liq < 5000 or vol_24h < 1000:
            confidence_tier = "ultra_low"
        elif liq < 20000 or vol_24h < 5000:
            confidence_tier = "low"
        elif liq < 50000 or mcap < 50000:
            confidence_tier = "medium"

        tier_multiplier = {"full": 1.0, "medium": 0.7, "low": 0.4, "ultra_low": 0.15}
        composite *= tier_multiplier.get(confidence_tier, 1.0)

        composite = max(0.0, min(composite, 1.0))

        if total_1h > 0:
            buy_ratio_1h = buys_1h / total_1h
        else:
            buy_ratio_1h = 0.5

        scored = {
            "pair": f"{pair.get('base_token', {}).get('symbol', '?')}/{pair.get('quote_token', {}).get('symbol', '?')}",
            "chain": chain,
            "composite_score": round(composite, 3),
            "confidence_tier": confidence_tier,
            "component_scores": {k: round(v, 3) for k, v in scores.items()},
            "price_usd": pair.get("price_usd", 0),
            "volume_24h": vol_24h,
            "liquidity_usd": liq,
            "market_cap": mcap,
            "buy_ratio_24h": round(buys_24h / total_txns, 3) if total_txns else 0,
            "buy_ratio_1h": round(buy_ratio_1h, 3),
            "signal": "STRONG_BUY" if composite >= 0.6 else "BUY" if composite >= 0.4 else "NEUTRAL" if composite >= 0.2 else "AVOID",
            "cex_listing_likelihood": "HIGH" if composite >= 0.6 else "MEDIUM" if composite >= 0.4 else "LOW",
        }
        # Preserve all original fields from the input pair (including base_token, mint, etc.)
        for k, v in pair.items():
            if k not in scored:
                scored[k] = v
        return scored

    def rank_pairs(self, pairs: List[Dict[str, Any]], top_n: int = 20) -> List[Dict[str, Any]]:
        scored = [self.score_pair(p) for p in pairs]
        scored.sort(key=lambda x: x["composite_score"], reverse=True)
        return scored[:top_n]
