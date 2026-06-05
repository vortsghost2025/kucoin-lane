import json
import os
import tempfile
from datetime import datetime, timezone, timedelta

import pytest

from src.intelligence.lead_lag import (
    DexToCexLagDetector,
    DEFAULT_DEX_TO_CEX_LAG_DAYS,
    DEFAULT_DEX_BACKTEST_GLOB,
    DEFAULT_KUCOIN_LISTINGS_PATH,
)


@pytest.fixture
def tmp_listings(tmp_path):
    listings = {
        "listings": [
            {"symbol": "WIF", "date": "2024-03-01", "chain": "solana"},
            {"symbol": "POPCAT", "date": "2024-07-15", "chain": "solana"},
            {"symbol": "BONK", "date": "2023-12-15", "chain": "solana"},
            {"symbol": "SOL", "date": "2020-08-01", "chain": "solana"},
        ],
        "source": "test",
        "last_updated": "2026-06-05",
    }
    p = tmp_path / "kucoin_listings.json"
    p.write_text(json.dumps(listings), encoding="utf-8")
    return str(p)


@pytest.fixture
def tmp_backtest(tmp_path):
    bt = {
        "total_scans": 30,
        "total_signals": 5,
        "signals_with_performance": [
            {
                "scan_time": "2024-02-15T10:00:00Z",
                "pair": "WIF/SOL",
                "base_token": "WIF",
                "composite_score": 0.72,
                "signal": "STRONG_BUY",
                "confidence_tier": "full",
                "listed_on_kucoin": True,
                "listing_date": "2024-03-01",
                "price_performance": None,
            },
            {
                "scan_time": "2024-02-16T10:00:00Z",
                "pair": "WIF/SOL",
                "base_token": "WIF",
                "composite_score": 0.71,
                "signal": "STRONG_BUY",
                "confidence_tier": "full",
                "listed_on_kucoin": True,
                "listing_date": "2024-03-01",
                "price_performance": None,
            },
            {
                "scan_time": "2024-07-08T10:00:00Z",
                "pair": "POPCAT/SOL",
                "base_token": "POPCAT",
                "composite_score": 0.55,
                "signal": "BUY",
                "confidence_tier": "medium",
                "listed_on_kucoin": True,
                "listing_date": "2024-07-15",
                "price_performance": None,
            },
            {
                "scan_time": "2026-06-04T10:00:00Z",
                "pair": "JOBLESS/SOL",
                "base_token": "JOBLESS",
                "composite_score": 0.44,
                "signal": "BUY",
                "confidence_tier": "medium",
                "listed_on_kucoin": False,
                "listing_date": None,
                "price_performance": None,
            },
            {
                "scan_time": "2026-06-04T10:00:00Z",
                "pair": "ZEST/USDT",
                "base_token": "ZEST",
                "composite_score": 0.63,
                "signal": "STRONG_BUY",
                "confidence_tier": "full",
                "listed_on_kucoin": False,
                "listing_date": None,
                "price_performance": None,
            },
            {
                "scan_time": "2026-06-04T10:00:00Z",
                "pair": "LOWSCORE/SOL",
                "base_token": "LOWSCORE",
                "composite_score": 0.10,
                "signal": "NEUTRAL",
                "confidence_tier": "ultra_low",
                "listed_on_kucoin": False,
                "listing_date": None,
                "price_performance": None,
            },
        ],
    }
    p = tmp_path / "dex_backtest_test.json"
    p.write_text(json.dumps(bt), encoding="utf-8")
    return str(p)


class TestDexToCexLagDetectorInit:
    def test_default_params(self):
        d = DexToCexLagDetector()
        assert d.lag_window_days == DEFAULT_DEX_TO_CEX_LAG_DAYS
        assert d.backtest_glob == DEFAULT_DEX_BACKTEST_GLOB
        assert d.listings_path == DEFAULT_KUCOIN_LISTINGS_PATH
        assert d.min_composite_score == 0.4
        assert d.dex_signals == []
        assert d.cex_listings == {}

    def test_custom_params(self):
        d = DexToCexLagDetector(
            lag_window_days=14,
            min_composite_score=0.5,
            backtest_glob="custom/*.json",
            listings_path="custom/listings.json",
        )
        assert d.lag_window_days == 14
        assert d.min_composite_score == 0.5
        assert d.backtest_glob == "custom/*.json"
        assert d.listings_path == "custom/listings.json"


class TestLoadKucoinListings:
    def test_missing_file(self, tmp_path):
        d = DexToCexLagDetector(listings_path=str(tmp_path / "nope.json"))
        assert d.load_kucoin_listings() is False
        assert d.cex_listings == {}

    def test_valid_file(self, tmp_listings):
        d = DexToCexLagDetector(listings_path=tmp_listings)
        assert d.load_kucoin_listings() is True
        assert "WIF" in d.cex_listings
        assert d.cex_listings["WIF"]["date"] == "2024-03-01"
        assert d.cex_listings["WIF"]["chain"] == "solana"

    def test_malformed_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid", encoding="utf-8")
        d = DexToCexLagDetector(listings_path=str(p))
        assert d.load_kucoin_listings() is False
        assert d.cex_listings == {}


class TestLoadDexBacktest:
    def test_explicit_path(self, tmp_backtest):
        d = DexToCexLagDetector()
        loaded = d.load_dex_backtest(path=tmp_backtest)
        assert len(loaded) == 5
        assert d.dex_signals == loaded

    def test_filters_below_min_composite(self, tmp_backtest):
        d = DexToCexLagDetector(min_composite_score=0.4)
        loaded = d.load_dex_backtest(path=tmp_backtest)
        assert len(loaded) == 5
        tokens = [s["base_token"] for s in loaded]
        assert "LOWSCORE" not in tokens

    def test_missing_file(self):
        d = DexToCexLagDetector(backtest_glob="/nonexistent/*.json")
        loaded = d.load_dex_backtest()
        assert loaded == []
        assert d.dex_signals == []

    def test_picks_latest_from_glob(self, tmp_path):
        for i in range(3):
            p = tmp_path / f"dex_backtest_2026060{i}_120000.json"
            p.write_text(json.dumps({
                "signals_with_performance": [
                    {"scan_time": "2024-01-01T00:00:00Z", "pair": f"T{i}/S",
                     "base_token": f"T{i}", "composite_score": 0.5,
                     "signal": "BUY", "confidence_tier": "medium"}
                ]
            }), encoding="utf-8")
        d = DexToCexLagDetector(backtest_glob=str(tmp_path / "dex_backtest_*.json"))
        loaded = d.load_dex_backtest()
        assert len(loaded) == 1
        assert loaded[0]["base_token"] == "T2"


class TestDetect:
    def test_opportunity_within_window(self, tmp_listings, tmp_backtest):
        d = DexToCexLagDetector(
            lag_window_days=30,
            listings_path=tmp_listings,
        )
        d.load_kucoin_listings()
        d.load_dex_backtest(path=tmp_backtest)
        signals = d.detect()
        wif = next(s for s in signals if s["base_token"] == "WIF")
        assert wif["lead_lag_signal"] == "OPPORTUNITY"
        assert wif["lag_days"] in (14, 15)
        assert wif["cex_listing_date"] == "2024-03-01"
        assert wif["chain"] == "solana"
        assert 0.0 <= wif["confidence"] <= 1.0
        assert "before KuCoin listing" in wif["rationale"]

    def test_watch_when_not_listed(self, tmp_listings, tmp_backtest):
        d = DexToCexLagDetector(
            lag_window_days=30,
            listings_path=tmp_listings,
        )
        d.load_kucoin_listings()
        d.load_dex_backtest(path=tmp_backtest)
        signals = d.detect()
        jobless = next(s for s in signals if s["base_token"] == "JOBLESS")
        assert jobless["lead_lag_signal"] == "WATCH"
        assert jobless["cex_listing_date"] is None
        assert jobless["lag_days"] is None
        assert "not yet on KuCoin" in jobless["rationale"]

    def test_dedupes_repeated_signals(self, tmp_listings, tmp_backtest):
        d = DexToCexLagDetector(
            lag_window_days=30,
            listings_path=tmp_listings,
        )
        d.load_kucoin_listings()
        d.load_dex_backtest(path=tmp_backtest)
        signals = d.detect()
        wif_count = sum(1 for s in signals if s["base_token"] == "WIF")
        assert wif_count == 1
        wif = next(s for s in signals if s["base_token"] == "WIF")
        assert "2024-02-15" in wif["dex_signal_date"]

    def test_signal_shape_opportunity(self, tmp_listings, tmp_backtest):
        d = DexToCexLagDetector(listings_path=tmp_listings)
        d.load_kucoin_listings()
        d.load_dex_backtest(path=tmp_backtest)
        signals = d.detect()
        opp = next(s for s in signals if s["lead_lag_signal"] == "OPPORTUNITY")
        required = {
            "base_token", "chain", "dex_pair", "dex_signal_date",
            "cex_listing_date", "lag_days", "dex_composite_score",
            "dex_confidence_tier", "lead_lag_signal", "confidence", "rationale",
        }
        assert required.issubset(set(opp.keys()))

    def test_signal_shape_watch(self, tmp_listings, tmp_backtest):
        d = DexToCexLagDetector(listings_path=tmp_listings)
        d.load_kucoin_listings()
        d.load_dex_backtest(path=tmp_backtest)
        signals = d.detect()
        watch = next(s for s in signals if s["lead_lag_signal"] == "WATCH")
        assert watch["cex_listing_date"] is None
        assert watch["lag_days"] is None
        assert watch["lead_lag_signal"] == "WATCH"

    def test_confidence_higher_for_tighter_lag(self, tmp_listings, tmp_backtest):
        d = DexToCexLagDetector(
            lag_window_days=30,
            listings_path=tmp_listings,
        )
        d.load_kucoin_listings()
        d.load_dex_backtest(path=tmp_backtest)
        signals = d.detect()
        opps = [s for s in signals if s["lead_lag_signal"] == "OPPORTUNITY"]
        assert len(opps) >= 2
        wif = next(s for s in opps if s["base_token"] == "WIF")
        popcat = next(s for s in opps if s["base_token"] == "POPCAT")
        assert popcat["lag_days"] < wif["lag_days"]
        assert popcat["confidence"] > wif["confidence"]

    def test_stale_when_listing_predates_signal(self, tmp_listings, tmp_path):
        bt = {
            "signals_with_performance": [
                {"scan_time": "2024-08-01T00:00:00Z", "pair": "BONK/SOL",
                 "base_token": "BONK", "composite_score": 0.5,
                 "signal": "BUY", "confidence_tier": "medium"},
            ]
        }
        bp = tmp_path / "bt.json"
        bp.write_text(json.dumps(bt), encoding="utf-8")
        d = DexToCexLagDetector(listings_path=tmp_listings)
        d.load_kucoin_listings()
        d.load_dex_backtest(path=str(bp))
        signals = d.detect()
        bonk = next(s for s in signals if s["base_token"] == "BONK")
        assert bonk["lead_lag_signal"] == "STALE"
        assert bonk["lag_days"] < 0

    def test_detect_requires_loaded_data(self, tmp_listings, tmp_backtest):
        d = DexToCexLagDetector(listings_path=tmp_listings)
        with pytest.raises(RuntimeError, match="must be loaded before calling detect"):
            d.detect()

    def test_run_convenience(self, tmp_listings, tmp_backtest):
        d = DexToCexLagDetector(
            lag_window_days=30,
            listings_path=tmp_listings,
            backtest_glob=os.path.dirname(tmp_backtest) + "/*.json",
        )
        signals = d.run(backtest_path=tmp_backtest)
        assert len(signals) > 0
        assert any(s["lead_lag_signal"] == "OPPORTUNITY" for s in signals)

    def test_get_status(self):
        d = DexToCexLagDetector(lag_window_days=7)
        status = d.get_status()
        assert status["lag_window_days"] == 7
        assert status["min_composite_score"] == 0.4
        assert status["dex_signals_loaded"] == 0
        assert status["cex_listings_loaded"] == 0


class TestEndToEndRealFiles:
    def test_run_on_actual_backtest_and_listings(self):
        test_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(test_dir)
        listings_path = os.path.join(repo_root, "data", "kucoin_listings.json")
        backtest_glob = os.path.join(repo_root, "reports", "dex_backtest_*.json")
        if not os.path.exists(listings_path):
            pytest.skip(f"data/kucoin_listings.json not present at {listings_path}")
        import glob as g
        if not g.glob(backtest_glob):
            pytest.skip(f"no reports/dex_backtest_*.json present at {backtest_glob}")
        d = DexToCexLagDetector(
            lag_window_days=30,
            listings_path=listings_path,
            backtest_glob=backtest_glob,
        )
        signals = d.run()
        assert len(signals) > 0
        token_types = {s["lead_lag_signal"] for s in signals}
        assert token_types.issubset({"OPPORTUNITY", "WATCH", "STALE"})
        assert any(s["confidence"] >= 0.0 for s in signals)
