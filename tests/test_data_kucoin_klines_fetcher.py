"""Tests for KuCoinKlinesFetcher — OHLCV conversion, caching, and edge cases."""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.data.kucoin_klines_fetcher import KuCoinKlinesFetcher, SUPPORTED_INTERVALS


class TestRawKlinesToDataFrame:
    """Test the static raw_klines_to_dataframe conversion method."""

    def test_empty_input(self):
        df = KuCoinKlinesFetcher.raw_klines_to_dataframe([])
        assert df.empty
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]

    def test_single_candle(self):
        # KuCoin format: [timestamp, open, close, high, low, volume_base, volume_quote]
        raw = [[
            "1700000000",  # timestamp
            "100.0",       # open
            "105.0",       # close (NOTE: this is close, not high!)
            "106.0",       # high
            "99.0",        # low
            "500.0",       # volume (base)
            "50000.0",     # volume (quote)
        ]]
        df = KuCoinKlinesFetcher.raw_klines_to_dataframe(raw)
        assert len(df) == 1
        assert df["open"].iloc[0] == 100.0
        assert df["high"].iloc[0] == 106.0
        assert df["low"].iloc[0] == 99.0
        assert df["close"].iloc[0] == 105.0
        assert df["volume"].iloc[0] == 500.0

    def test_multiple_candles_sorted(self):
        # Provide candles out of order — should be sorted by timestamp ascending
        raw = [
            ["1700000100", "101.0", "102.0", "103.0", "100.0", "200.0", "20000.0"],
            ["1700000000", "100.0", "101.0", "102.0", "99.0", "100.0", "10000.0"],
            ["1700000200", "102.0", "103.0", "104.0", "101.0", "300.0", "30000.0"],
        ]
        df = KuCoinKlinesFetcher.raw_klines_to_dataframe(raw)
        assert len(df) == 3
        # Should be sorted: oldest first
        assert df["open"].iloc[0] == 100.0
        assert df["open"].iloc[1] == 101.0
        assert df["open"].iloc[2] == 102.0

    def test_kucoin_field_order_not_standard_ohlcv(self):
        """Verify the critical KuCoin field order: [ts, open, CLOSE, HIGH, LOW, vol]."""
        raw = [[
            "1700000000",
            "50.0",   # open
            "48.0",   # close (KuCoin puts this BEFORE high)
            "52.0",   # high
            "47.0",   # low
            "1000.0", # volume
            "50000.0", # quote volume
        ]]
        df = KuCoinKlinesFetcher.raw_klines_to_dataframe(raw)
        # Verify the swap happened correctly
        assert df["open"].iloc[0] == 50.0
        assert df["close"].iloc[0] == 48.0  # close stays close
        assert df["high"].iloc[0] == 52.0   # high is high (was at index 3)
        assert df["low"].iloc[0] == 47.0    # low is low (was at index 4)
        # Sanity: high >= low
        assert df["high"].iloc[0] >= df["low"].iloc[0]

    def test_malformed_candle_skipped(self):
        raw = [
            ["1700000000", "100.0", "101.0", "102.0", "99.0", "100.0", "10000.0"],
            ["bad_timestamp", "100.0", "101.0", "102.0", "99.0", "100.0"],  # malformed
            ["1700000100", "101.0", "102.0", "103.0", "100.0", "200.0", "20000.0"],
        ]
        df = KuCoinKlinesFetcher.raw_klines_to_dataframe(raw)
        assert len(df) == 2  # malformed row skipped

    def test_string_values_converted_to_float(self):
        raw = [[
            "1700000000",
            "100.5",
            "101.2",
            "102.8",
            "99.1",
            "500.0",
            "50000.0",
        ]]
        df = KuCoinKlinesFetcher.raw_klines_to_dataframe(raw)
        assert df["open"].iloc[0] == 100.5
        assert df["close"].iloc[0] == 101.2

    def test_regime_detector_compatible_columns(self):
        """The DataFrame must have 'high', 'low', 'close' columns for RegimeDetector."""
        raw = [[
            str(1700000000 + i * 300),
            str(100.0 + i),
            str(101.0 + i),
            str(102.0 + i),
            str(99.0 + i),
            "1000.0",
            "100000.0",
        ] for i in range(30)]
        df = KuCoinKlinesFetcher.raw_klines_to_dataframe(raw)
        # RegimeDetector requires these exact columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "close" in df.columns
        # WhaleWatch requires 'open' for CVD estimation
        assert "open" in df.columns
        assert "volume" in df.columns


class TestKuCoinKlinesFetcher:
    """Test the KuCoinKlinesFetcher class."""

    @pytest.fixture
    def fetcher(self):
        return KuCoinKlinesFetcher(default_interval="5min", default_candle_count=100)

    @pytest.fixture
    def mock_adapter(self):
        adapter = MagicMock()
        # Return 30 candles of realistic KuCoin-format data
        adapter.get_klines.return_value = [
            [
                str(1700000000 + i * 300),
                str(100.0 + i * 0.5),
                str(100.5 + i * 0.5),
                str(101.0 + i * 0.5),
                str(99.5 + i * 0.5),
                str(1000.0 + i * 10),
                str(100000.0 + i * 1000),
            ]
            for i in range(30)
        ]
        return adapter

    def test_init_defaults(self, fetcher):
        assert fetcher.default_interval == "5min"
        assert fetcher.default_candle_count == 100
        assert fetcher.cache_enabled is True

    def test_fetch_klines_success(self, fetcher, mock_adapter):
        df = fetcher.fetch_klines(mock_adapter, "SOL/USDT")
        assert df is not None
        assert not df.empty
        assert len(df) == 30
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "close" in df.columns
        mock_adapter.get_klines.assert_called_once()

    def test_fetch_klines_caching(self, fetcher, mock_adapter):
        # First call — hits adapter
        df1 = fetcher.fetch_klines(mock_adapter, "SOL/USDT")
        # Second call — should use cache (within 300s timeout for 5min)
        df2 = fetcher.fetch_klines(mock_adapter, "SOL/USDT")
        # Adapter should only be called once (second uses cache)
        assert mock_adapter.get_klines.call_count == 1
        assert len(df1) == len(df2)

    def test_fetch_klines_unsupported_interval(self, fetcher, mock_adapter):
        df = fetcher.fetch_klines(mock_adapter, "SOL/USDT", interval="10min")
        assert df is None
        mock_adapter.get_klines.assert_not_called()

    def test_fetch_klines_empty_response(self, fetcher, mock_adapter):
        mock_adapter.get_klines.return_value = []
        df = fetcher.fetch_klines(mock_adapter, "SOL/USDT")
        assert df is None

    def test_fetch_klines_adapter_exception(self, fetcher, mock_adapter):
        mock_adapter.get_klines.side_effect = Exception("API error")
        df = fetcher.fetch_klines(mock_adapter, "SOL/USDT")
        assert df is None

    def test_fetch_klines_multi(self, fetcher, mock_adapter):
        results = fetcher.fetch_klines_multi(
            mock_adapter, ["SOL/USDT", "BTC/USDT"]
        )
        assert "SOL/USDT" in results
        assert "BTC/USDT" in results
        assert mock_adapter.get_klines.call_count == 2

    def test_fetch_klines_multi_partial_failure(self, fetcher, mock_adapter):
        call_count = [0]

        def side_effect(symbol, interval, start=None, end=None):
            call_count[0] += 1
            if "BTC" in symbol:
                return []  # empty response
            return mock_adapter.get_klines.return_value

        mock_adapter.get_klines.side_effect = side_effect
        results = fetcher.fetch_klines_multi(
            mock_adapter, ["SOL/USDT", "BTC/USDT"]
        )
        assert "SOL/USDT" in results
        assert "BTC/USDT" not in results

    def test_clear_cache(self, fetcher, mock_adapter):
        fetcher.fetch_klines(mock_adapter, "SOL/USDT")
        assert len(fetcher._cache) == 1
        fetcher.clear_cache()
        assert len(fetcher._cache) == 0

    def test_get_cache_status(self, fetcher, mock_adapter):
        fetcher.fetch_klines(mock_adapter, "SOL/USDT")
        status = fetcher.get_cache_status()
        assert status["total_entries"] == 1
        assert "SOL/USDT_5min" in status["entries"]

    def test_interval_to_seconds(self, fetcher):
        assert fetcher._interval_to_seconds("5min") == 300
        assert fetcher._interval_to_seconds("1hour") == 3600
        assert fetcher._interval_to_seconds("1day") == 86400
        assert fetcher._interval_to_seconds("1week") == 604800


class TestKlinesWithRegimeDetector:
    """Integration: feed klines fetcher output directly into RegimeDetector."""

    def test_klines_feed_into_regime_detector(self):
        """Verify the DataFrame from raw_klines_to_dataframe works with RegimeDetector."""
        from src.intelligence.regime_detector import RegimeDetector

        # Generate 30 candles of trending data
        raw = [
            [
                str(1700000000 + i * 300),
                str(100.0 + i * 2),  # open trending up
                str(101.0 + i * 2),  # close
                str(102.0 + i * 2),  # high
                str(99.0 + i * 2),   # low
                str(1000.0),
                str(100000.0),
            ]
            for i in range(30)
        ]
        df = KuCoinKlinesFetcher.raw_klines_to_dataframe(raw)
        detector = RegimeDetector(adx_period=14, atr_period=14)
        result = detector.analyze(df)
        # Should not return UNKNOWN since we have 30 candles
        assert result["regime"] != "UNKNOWN"
        assert "adx" in result
        assert "atr_pct" in result
        assert "recommendation" in result

    def test_klines_feed_into_whale_watch(self):
        """Verify the DataFrame from raw_klines_to_dataframe works with WhaleWatch."""
        from src.intelligence.whale_watch import WhaleWatch

        raw = [
            [
                str(1700000000 + i * 300),
                str(100.0 + i * 0.5),
                str(100.5 + i * 0.5),
                str(101.0 + i * 0.5),
                str(99.5 + i * 0.5),
                str(1000.0),
                str(100000.0),
            ]
            for i in range(30)
        ]
        df = KuCoinKlinesFetcher.raw_klines_to_dataframe(raw)
        ww = WhaleWatch()
        result = ww.analyze_order_flow(df)
        assert "signal" in result
        assert "confidence" in result
        assert "cvd_ratio" in result
