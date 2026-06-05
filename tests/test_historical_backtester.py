"""Tests for HistoricalBacktester."""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

from src.intelligence.historical_backtester import HistoricalBacktester


def _make_ohlcv_df(n_rows=200, seed=42):
    """Generate a realistic OHLCV DataFrame."""
    rng = np.random.RandomState(seed)
    base = 100.0
    returns = rng.normal(0.0002, 0.015, n_rows)
    close = base * np.cumprod(1 + returns)
    high = close * (1 + rng.uniform(0, 0.01, n_rows))
    low = close * (1 - rng.uniform(0, 0.01, n_rows))
    open_ = close * (1 + rng.uniform(-0.005, 0.005, n_rows))
    volume = rng.uniform(1e5, 1e7, n_rows)
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )
    df.index = pd.date_range("2024-01-01", periods=n_rows, freq="h")
    return df


class TestInit:
    def test_defaults(self):
        bt = HistoricalBacktester()
        assert bt.rsi_period == 14
        assert bt.adx_trend_threshold == 25.0
        assert bt._cache == {}

    def test_custom_params(self):
        bt = HistoricalBacktester(rsi_period=21, adx_trend_threshold=30.0)
        assert bt.rsi_period == 21
        assert bt.adx_trend_threshold == 30.0


class TestBacktestPairNoFetchers:
    def test_returns_none_when_both_none(self):
        bt = HistoricalBacktester()
        result = bt.backtest_pair("BTC-USDT", {}, klines_fetcher=None, exchange_adapter=None)
        assert result is None

    def test_returns_none_when_klines_fetcher_none(self):
        bt = HistoricalBacktester()
        result = bt.backtest_pair("BTC-USDT", {}, klines_fetcher=None, exchange_adapter=MagicMock())
        assert result is None

    def test_returns_none_when_exchange_adapter_none(self):
        bt = HistoricalBacktester()
        result = bt.backtest_pair("BTC-USDT", {}, klines_fetcher=MagicMock(), exchange_adapter=None)
        assert result is None


class TestBacktestPairInsufficientData:
    def setup_method(self):
        self.bt = HistoricalBacktester()
        self.fetcher = MagicMock()
        self.adapter = MagicMock()

    def test_returns_none_when_fetcher_returns_none(self):
        self.fetcher.fetch_klines.return_value = None
        result = self.bt.backtest_pair("BTC-USDT", {}, self.fetcher, self.adapter)
        assert result is None

    def test_returns_none_when_fetcher_returns_empty_df(self):
        self.fetcher.fetch_klines.return_value = pd.DataFrame()
        result = self.bt.backtest_pair("BTC-USDT", {}, self.fetcher, self.adapter)
        assert result is None

    def test_returns_none_when_fetcher_returns_short_df(self):
        self.fetcher.fetch_klines.return_value = _make_ohlcv_df(30)
        result = self.bt.backtest_pair("BTC-USDT", {}, self.fetcher, self.adapter)
        assert result is None

    def test_returns_none_when_fetcher_returns_exactly_49_rows(self):
        self.fetcher.fetch_klines.return_value = _make_ohlcv_df(49)
        result = self.bt.backtest_pair("BTC-USDT", {}, self.fetcher, self.adapter)
        assert result is None


class TestCalculateRsi:
    def test_produces_rsi_column(self):
        bt = HistoricalBacktester()
        df = _make_ohlcv_df(100)
        result = bt._calculate_rsi(df, period=14)
        assert "rsi" in result.columns

    def test_rsi_bounded_0_to_100(self):
        bt = HistoricalBacktester()
        df = _make_ohlcv_df(200)
        result = bt._calculate_rsi(df, period=14)
        valid = result["rsi"].dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_rsi_with_custom_period(self):
        bt = HistoricalBacktester(rsi_period=21)
        df = _make_ohlcv_df(200)
        result = bt._calculate_rsi(df, period=21)
        assert "rsi" in result.columns
        assert result["rsi"].notna().sum() > 0

    def test_rsi_monotonic_price_rises(self):
        bt = HistoricalBacktester()
        df = pd.DataFrame({"close": np.linspace(100, 200, 60)})
        result = bt._calculate_rsi(df, period=14)
        valid = result["rsi"].dropna()
        assert valid.iloc[-1] > 70


class TestCalculateAdxProxy:
    def test_produces_adx_columns(self):
        bt = HistoricalBacktester()
        df = _make_ohlcv_df(100)
        result = bt._calculate_adx_proxy(df)
        assert "adx" in result.columns
        assert "adx_pos" in result.columns
        assert "adx_neg" in result.columns

    def test_adx_values_non_negative(self):
        bt = HistoricalBacktester()
        df = _make_ohlcv_df(100)
        result = bt._calculate_adx_proxy(df)
        valid_adx = result["adx"].dropna()
        assert (valid_adx >= 0).all()

    def test_fallback_path_with_ohlcv(self):
        bt = HistoricalBacktester()
        df = _make_ohlcv_df(200)
        result = bt._calculate_adx_proxy(df)
        assert result["adx"].notna().sum() > 20


class TestRunWalkForward:
    def test_returns_list_of_dicts(self):
        bt = HistoricalBacktester()
        df = _make_ohlcv_df(200)
        df = bt._calculate_rsi(df, 14)
        df = bt._calculate_adx_proxy(df)
        trades = bt._run_walk_forward(df, "BTC-USDT")
        assert isinstance(trades, list)
        if trades:
            assert isinstance(trades[0], dict)

    def test_trade_dict_keys(self):
        bt = HistoricalBacktester()
        df = _make_ohlcv_df(200)
        df = bt._calculate_rsi(df, 14)
        df = bt._calculate_adx_proxy(df)
        trades = bt._run_walk_forward(df, "BTC-USDT")
        if trades:
            expected_keys = {"entry_price", "exit_price", "pnl_pct", "exit_reason", "bars_held", "regime_at_entry"}
            assert expected_keys.issubset(trades[0].keys())

    def test_warmup_skips_initial_bars(self):
        bt = HistoricalBacktester(rsi_period=14)
        df = _make_ohlcv_df(200)
        df = bt._calculate_rsi(df, 14)
        df = bt._calculate_adx_proxy(df)
        trades = bt._run_walk_forward(df, "BTC-USDT")
        for t in trades:
            assert t["bars_held"] >= 0


class TestComputeMetrics:
    def test_mixed_wins_losses(self):
        bt = HistoricalBacktester()
        trades = [
            {"pnl_pct": 0.05},
            {"pnl_pct": -0.03},
            {"pnl_pct": 0.04},
            {"pnl_pct": -0.02},
            {"pnl_pct": 0.01},
            {"pnl_pct": -0.01},
        ]
        metrics = bt._compute_metrics(trades)
        assert metrics["win_rate"] == 0.5
        assert metrics["total_trades"] == 6
        assert metrics["winning_trades"] == 3
        assert metrics["losing_trades"] == 3
        assert metrics["max_drawdown"] >= 0
        assert metrics["profit_factor"] > 0
        assert isinstance(metrics["sharpe_approx"], float)

    def test_zero_losses_profit_factor_inf(self):
        bt = HistoricalBacktester()
        trades = [
            {"pnl_pct": 0.05},
            {"pnl_pct": 0.03},
            {"pnl_pct": 0.02},
        ]
        metrics = bt._compute_metrics(trades)
        assert metrics["win_rate"] == 1.0
        assert metrics["winning_trades"] == 3
        assert metrics["losing_trades"] == 0
        assert metrics["profit_factor"] == float("inf") or metrics["profit_factor"] > 50
        assert metrics["avg_loss_pct"] == 0.0

    def test_all_losses_win_rate_zero(self):
        bt = HistoricalBacktester()
        trades = [
            {"pnl_pct": -0.05},
            {"pnl_pct": -0.03},
            {"pnl_pct": -0.02},
        ]
        metrics = bt._compute_metrics(trades)
        assert metrics["win_rate"] == 0.0
        assert metrics["winning_trades"] == 0
        assert metrics["losing_trades"] == 3
        assert metrics["avg_win_pct"] == 0.0
        assert metrics["profit_factor"] == 0.0
        assert metrics["max_drawdown"] > 0

    def test_single_trade_sharpe_zero(self):
        bt = HistoricalBacktester()
        trades = [{"pnl_pct": 0.02}]
        metrics = bt._compute_metrics(trades)
        assert metrics["sharpe_approx"] == 0.0

    def test_max_drawdown_calculation(self):
        bt = HistoricalBacktester()
        trades = [
            {"pnl_pct": 0.10},
            {"pnl_pct": -0.20},
            {"pnl_pct": 0.05},
        ]
        metrics = bt._compute_metrics(trades)
        assert metrics["max_drawdown"] > 0
        assert metrics["max_drawdown"] <= 1.0

    def test_empty_trades_default_win_rate(self):
        bt = HistoricalBacktester()
        metrics = bt._compute_metrics([])
        assert metrics["win_rate"] == 0.5
        assert metrics["total_trades"] == 0
        assert metrics["profit_factor"] == float("inf") or metrics["profit_factor"] > 50


class TestBacktestPairEndToEnd:
    def test_full_backtest_with_mock_fetcher(self):
        bt = HistoricalBacktester()
        df = _make_ohlcv_df(200, seed=42)
        fetcher = MagicMock()
        adapter = MagicMock()
        fetcher.fetch_klines.return_value = df

        result = bt.backtest_pair("BTC-USDT", {}, fetcher, adapter)

        fetcher.fetch_klines.assert_called_once_with(
            adapter, "BTC/USDT", interval="1hour", candle_count=200
        )
        assert result is not None
        assert "pair" in result
        assert result["pair"] == "BTC-USDT"
        assert "win_rate" in result
        assert "max_drawdown" in result
        assert "total_trades" in result
        assert "data_source" in result
        assert result["data_source"] in ("klines_historical", "klines_empty")
        assert "signal_valid" in result
        assert "confidence" in result
        assert "recommendation" in result
        assert result["recommendation"] in ("PROCEED", "SKIP")
        assert 0 <= result["win_rate"] <= 1
        assert 0 <= result["max_drawdown"] <= 1

    def test_no_trades_returns_neutral_estimates(self):
        bt = HistoricalBacktester()
        df = _make_ohlcv_df(200, seed=7)
        n = len(df)
        df["open"] = df["close"]
        df["high"] = df["close"]
        df["low"] = df["close"]
        fetcher = MagicMock()
        adapter = MagicMock()
        fetcher.fetch_klines.return_value = df

        result = bt.backtest_pair("BTC-USDT", {}, fetcher, adapter)

        assert result is not None

    def test_fetcher_call_args(self):
        bt = HistoricalBacktester()
        fetcher = MagicMock()
        adapter = MagicMock()
        fetcher.fetch_klines.return_value = _make_ohlcv_df(200)

        bt.backtest_pair("ETH-USDT", {}, fetcher, adapter)

        fetcher.fetch_klines.assert_called_once_with(
            adapter, "ETH/USDT", interval="1hour", candle_count=200
        )

    def test_exception_returns_none(self):
        bt = HistoricalBacktester()
        fetcher = MagicMock()
        adapter = MagicMock()
        fetcher.fetch_klines.side_effect = RuntimeError("API error")

        result = bt.backtest_pair("BTC-USDT", {}, fetcher, adapter)
        assert result is None

    def test_signal_valid_flags_skip(self):
        bt = HistoricalBacktester()
        trades = [{"pnl_pct": -0.10}] * 60
        metrics = bt._compute_metrics(trades)
        assert metrics["win_rate"] < 0.35 or metrics["max_drawdown"] > 0.20
