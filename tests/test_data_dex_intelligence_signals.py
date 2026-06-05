import pytest
from src.data.dex_intelligence import signals


class TestDexSignalScorer:
    def test_init(self):
        scorer = signals.DexSignalScorer()
        assert scorer.weights["volume_spike"] == 0.25
        assert scorer.weights["tx_ratio"] == 0.15
        assert scorer.weights["liquidity_depth"] == 0.15
        assert scorer.weights["age_penalty"] == 0.10
        assert scorer.weights["chain_multiplier"] == 0.10
        assert scorer.weights["graduation_signal"] == 0.15
        assert scorer.weights["volume_mcap_ratio"] == 0.10
        assert abs(sum(scorer.weights.values()) - 1.0) < 0.001

    def test_constants(self):
        assert signals.DexSignalScorer.MIN_LIQUIDITY_USD == 50000.0
        assert signals.DexSignalScorer.MIN_VOLUME_USD == 10000.0
        assert signals.DexSignalScorer.MIN_MCAP_USD == 100000.0

    def test_score_pair_empty(self):
        scorer = signals.DexSignalScorer()
        result = scorer.score_pair({})
        assert result["composite_score"] >= 0.0
        assert result["composite_score"] < 0.05
        assert result["signal"] in ("AVOID", "NEUTRAL")
        assert result["confidence_tier"] == "ultra_low"
        assert result["pair"] == "?/?"
        assert result["chain"] == ""
        assert result["cex_listing_likelihood"] == "LOW"

    def test_score_pair_strong_solana_token(self):
        scorer = signals.DexSignalScorer()
        pair = {
            "base_token": {"symbol": "BONK"},
            "quote_token": {"symbol": "USDC"},
            "chain": "solana",
            "volume_24h": 1000000.0,
            "volume_6h": 300000.0,
            "volume_1h": 50000.0,
            "liquidity_usd": 200000.0,
            "market_cap": 5000000.0,
            "buys_24h": 800,
            "sells_24h": 200,
            "buys_1h": 40,
            "sells_1h": 10,
            "pair_created_at": 1715000000000,
            "price_usd": 0.000001,
            "graduated": True,
        }
        result = scorer.score_pair(pair)
        assert result["pair"] == "BONK/USDC"
        assert result["chain"] == "solana"
        assert result["confidence_tier"] == "full"
        assert result["composite_score"] >= 0.6
        assert result["signal"] == "STRONG_BUY"
        assert result["cex_listing_likelihood"] == "HIGH"
        assert result["buy_ratio_24h"] == 0.8
        assert result["buy_ratio_1h"] == 0.8

    def test_score_pair_buy_signal(self):
        scorer = signals.DexSignalScorer()
        pair = {
            "base_token": {"symbol": "WIF"},
            "quote_token": {"symbol": "USDC"},
            "chain": "solana",
            "volume_24h": 100000.0,
            "volume_6h": 25000.0,
            "liquidity_usd": 80000.0,
            "market_cap": 200000.0,
            "buys_24h": 100,
            "sells_24h": 80,
            "pair_created_at": 1715000000000,
        }
        result = scorer.score_pair(pair)
        assert result["composite_score"] >= 0.3
        assert result["signal"] in ("STRONG_BUY", "BUY", "NEUTRAL")
        assert result["confidence_tier"] in ("full", "medium")

    def test_score_pair_avoid_signal(self):
        scorer = signals.DexSignalScorer()
        pair = {
            "base_token": {"symbol": "SCAM"},
            "quote_token": {"symbol": "USDC"},
            "chain": "ethereum",
            "volume_24h": 100.0,
            "liquidity_usd": 1000.0,
            "market_cap": 5000.0,
        }
        result = scorer.score_pair(pair)
        assert result["signal"] == "AVOID"
        assert result["confidence_tier"] == "ultra_low"
        assert result["composite_score"] < 0.2

    def test_confidence_tier_thresholds(self):
        scorer = signals.DexSignalScorer()
        full = {"base_token": {"symbol": "A"}, "quote_token": {"symbol": "B"},
                "chain": "solana", "volume_24h": 100000, "liquidity_usd": 100000, "market_cap": 200000}
        medium = {"base_token": {"symbol": "B"}, "quote_token": {"symbol": "C"},
                  "chain": "solana", "volume_24h": 8000, "liquidity_usd": 30000, "market_cap": 80000}
        low = {"base_token": {"symbol": "C"}, "quote_token": {"symbol": "D"},
               "chain": "solana", "volume_24h": 3000, "liquidity_usd": 10000, "market_cap": 30000}
        ultra_low = {"base_token": {"symbol": "D"}, "quote_token": {"symbol": "E"},
                     "chain": "solana", "volume_24h": 500, "liquidity_usd": 2000, "market_cap": 5000}
        assert scorer.score_pair(full)["confidence_tier"] == "full"
        assert scorer.score_pair(medium)["confidence_tier"] in ("medium", "low")
        assert scorer.score_pair(low)["confidence_tier"] in ("low", "ultra_low")
        assert scorer.score_pair(ultra_low)["confidence_tier"] == "ultra_low"

    def test_chain_multiplier_values(self):
        scorer = signals.DexSignalScorer()
        for chain, expected in [("solana", 0.8), ("base", 0.6), ("ethereum", 0.5), ("arbitrum", 0.4), ("bsc", 0.3)]:
            pair = {"base_token": {"symbol": "X"}, "quote_token": {"symbol": "Y"},
                    "chain": chain, "volume_24h": 100000, "liquidity_usd": 100000, "market_cap": 200000}
            result = scorer.score_pair(pair)
            assert result["component_scores"]["chain_multiplier"] == expected

    def test_unknown_chain_low_multiplier(self):
        scorer = signals.DexSignalScorer()
        pair = {"base_token": {"symbol": "X"}, "quote_token": {"symbol": "Y"},
                "chain": "unknownchain", "volume_24h": 100000, "liquidity_usd": 100000, "market_cap": 200000}
        result = scorer.score_pair(pair)
        assert result["component_scores"]["chain_multiplier"] == 0.2

    def test_graduation_signal_full(self):
        scorer = signals.DexSignalScorer()
        pair = {"base_token": {"symbol": "G"}, "quote_token": {"symbol": "S"},
                "chain": "solana", "graduated": True, "volume_24h": 100000, "liquidity_usd": 100000}
        result = scorer.score_pair(pair)
        assert result["component_scores"]["graduation_signal"] == 1.0

    def test_graduation_signal_bonding_80(self):
        scorer = signals.DexSignalScorer()
        pair = {"base_token": {"symbol": "B"}, "quote_token": {"symbol": "S"},
                "chain": "solana", "bonding_progress_pct": 85, "volume_24h": 100000, "liquidity_usd": 100000}
        result = scorer.score_pair(pair)
        assert result["component_scores"]["graduation_signal"] == 0.7

    def test_graduation_signal_low(self):
        scorer = signals.DexSignalScorer()
        pair = {"base_token": {"symbol": "L"}, "quote_token": {"symbol": "S"},
                "chain": "solana", "bonding_progress_pct": 30, "volume_24h": 100000, "liquidity_usd": 100000}
        result = scorer.score_pair(pair)
        assert result["component_scores"]["graduation_signal"] == 0.0

    def test_rank_pairs_sorted_descending(self):
        scorer = signals.DexSignalScorer()
        pairs = [
            {"base_token": {"symbol": "LOW"}, "quote_token": {"symbol": "U"},
             "chain": "solana", "volume_24h": 100, "liquidity_usd": 100},
            {"base_token": {"symbol": "HIGH"}, "quote_token": {"symbol": "U"},
             "chain": "solana", "volume_24h": 1000000, "liquidity_usd": 500000, "market_cap": 2000000,
             "buys_24h": 1000, "sells_24h": 200, "graduated": True},
            {"base_token": {"symbol": "MID"}, "quote_token": {"symbol": "U"},
             "chain": "solana", "volume_24h": 50000, "liquidity_usd": 50000, "market_cap": 100000},
        ]
        ranked = scorer.rank_pairs(pairs, top_n=3)
        assert len(ranked) == 3
        assert ranked[0]["composite_score"] >= ranked[1]["composite_score"]
        assert ranked[1]["composite_score"] >= ranked[2]["composite_score"]
        assert ranked[0]["pair"] == "HIGH/U"

    def test_rank_pairs_top_n(self):
        scorer = signals.DexSignalScorer()
        pairs = [{"base_token": {"symbol": f"T{i}"}, "quote_token": {"symbol": "U"},
                  "chain": "solana", "volume_24h": 10000 * (i + 1),
                  "liquidity_usd": 100000, "market_cap": 200000} for i in range(50)]
        ranked = scorer.rank_pairs(pairs, top_n=5)
        assert len(ranked) == 5

    def test_composite_score_clamped(self):
        scorer = signals.DexSignalScorer()
        pair = {"base_token": {"symbol": "MOON"}, "quote_token": {"symbol": "U"},
                "chain": "solana", "volume_24h": 999999999, "liquidity_usd": 999999999,
                "market_cap": 999999999, "buys_24h": 10000, "sells_24h": 1, "graduated": True}
        result = scorer.score_pair(pair)
        assert 0.0 <= result["composite_score"] <= 1.0

    def test_volume_spike_detection(self):
        scorer = signals.DexSignalScorer()
        spike = {"base_token": {"symbol": "S"}, "quote_token": {"symbol": "U"},
                 "chain": "solana", "volume_24h": 100000, "volume_6h": 50000,
                 "liquidity_usd": 100000, "market_cap": 200000}
        no_spike = {"base_token": {"symbol": "N"}, "quote_token": {"symbol": "U"},
                    "chain": "solana", "volume_24h": 100000, "volume_6h": 20000,
                    "liquidity_usd": 100000, "market_cap": 200000}
        s_spike = scorer.score_pair(spike)["component_scores"]["volume_spike"]
        s_nospike = scorer.score_pair(no_spike)["component_scores"]["volume_spike"]
        assert s_spike > s_nospike

    def test_buy_ratio_calculation(self):
        scorer = signals.DexSignalScorer()
        bullish = {"base_token": {"symbol": "B"}, "quote_token": {"symbol": "U"},
                   "chain": "solana", "volume_24h": 100000, "liquidity_usd": 100000,
                   "buys_24h": 90, "sells_24h": 10}
        bearish = {"base_token": {"symbol": "X"}, "quote_token": {"symbol": "U"},
                   "chain": "solana", "volume_24h": 100000, "liquidity_usd": 100000,
                   "buys_24h": 10, "sells_24h": 90}
        assert scorer.score_pair(bullish)["buy_ratio_24h"] == 0.9
        assert scorer.score_pair(bearish)["buy_ratio_24h"] == 0.1
        assert scorer.score_pair(bullish)["composite_score"] > scorer.score_pair(bearish)["composite_score"]
