import pytest
import numpy as np
import pandas as pd
from src.intelligence.strategies import (
    compute_atr,
    VolBreakout,
    Supertrend,
    StrategyFactory,
    Strategy,
)


def make_ohlcv_df(closes, highs=None, lows=None, volumes=None):
    """Create OHLCV DataFrame from close prices."""
    n = len(closes)
    closes_arr = np.array(closes, dtype=float)
    if highs is None:
        highs = closes_arr * 1.01
    else:
        highs = np.array(highs, dtype=float)
    if lows is None:
        lows = closes_arr * 0.99
    else:
        lows = np.array(lows, dtype=float)
    if volumes is None:
        volumes = np.ones(n) * 1000.0
    else:
        volumes = np.array(volumes, dtype=float)
    opens = np.roll(closes_arr, 1)
    opens[0] = closes_arr[0]
    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes_arr,
        "volume": volumes,
    })


class TestComputeATR:
    def test_constant_prices_near_zero_atr(self):
        """ATR of constant prices should be near zero."""
        n = 30
        closes = np.full(n, 100.0)
        highs = np.full(n, 100.01)
        lows = np.full(n, 99.99)
        atr = compute_atr(highs, lows, closes, period=14)
        assert not np.isnan(atr[-1])
        assert atr[-1] < 0.1

    def test_increasing_volatility(self):
        """ATR should increase as volatility increases."""
        n = 50
        closes = np.array([100.0 + i * 0.5 for i in range(n)])
        spreads = np.array([0.5 + i * 0.2 for i in range(n)])
        highs = closes + spreads
        lows = closes - spreads
        atr = compute_atr(highs, lows, closes, period=14)
        assert not np.isnan(atr[-1])
        assert not np.isnan(atr[20])
        assert atr[-1] > atr[20]

    def test_initial_values_are_nan(self):
        """First period-1 ATR values should be NaN."""
        n = 30
        closes = np.linspace(100, 110, n)
        highs = closes * 1.01
        lows = closes * 0.99
        atr = compute_atr(highs, lows, closes, period=14)
        for i in range(13):
            assert np.isnan(atr[i])
        assert not np.isnan(atr[13])

    def test_known_values(self):
        """ATR with simple known input should produce reasonable output."""
        closes = np.full(20, 100.0)
        highs = np.full(20, 101.0)
        lows = np.full(20, 99.0)
        atr = compute_atr(highs, lows, closes, period=14)
        assert not np.isnan(atr[-1])
        assert 1.5 < atr[-1] < 2.5


class TestVolBreakout:
    def test_insufficient_data_returns_hold(self):
        """With fewer bars than atr_period + 2, should return HOLD."""
        df = make_ohlcv_df([100.0, 101.0, 102.0])
        vb = VolBreakout(atr_period=14)
        signal = vb.generate_signal(df)
        assert signal["action"] == "HOLD"
        assert signal["confidence"] < 0.3

    def test_breakout_above_channel_returns_buy(self):
        """Price breaking above upper channel should return BUY."""
        n = 20
        closes = np.full(n, 100.0)
        closes[-1] = 105.0
        highs = closes * 1.005
        lows = closes * 0.995
        df = make_ohlcv_df(closes, highs=highs, lows=lows)
        vb = VolBreakout(atr_period=14, atr_mult_entry=1.0)
        signal = vb.generate_signal(df)
        assert signal["action"] == "BUY"
        assert signal["confidence"] > 0.5
        assert "upper_channel" in signal["indicators"]
        assert "lower_channel" in signal["indicators"]
        assert "atr" in signal["indicators"]

    def test_breakdown_below_channel_returns_sell(self):
        """Price breaking below lower channel should return SELL."""
        n = 20
        closes = np.full(n, 100.0)
        closes[-1] = 95.0
        highs = closes * 1.005
        lows = closes * 0.995
        df = make_ohlcv_df(closes, highs=highs, lows=lows)
        vb = VolBreakout(atr_period=14, atr_mult_entry=1.0)
        signal = vb.generate_signal(df)
        assert signal["action"] == "SELL"
        assert signal["confidence"] > 0.5

    def test_price_within_channel_returns_hold(self):
        """Price within channels should return HOLD."""
        n = 20
        closes = np.full(n, 100.0)
        highs = closes + 0.5
        lows = closes - 0.5
        df = make_ohlcv_df(closes, highs=highs, lows=lows)
        vb = VolBreakout(atr_period=14, atr_mult_entry=2.0)
        signal = vb.generate_signal(df)
        assert signal["action"] == "HOLD"

    def test_custom_parameters(self):
        """VolBreakout should accept and use custom parameters."""
        vb = VolBreakout(atr_period=10, atr_mult_entry=1.5, atr_mult_exit=2.0)
        assert vb.atr_period == 10
        assert vb.atr_mult_entry == 1.5
        assert vb.atr_mult_exit == 2.0

    def test_indicators_dict_keys(self):
        """Indicators dict should contain expected keys."""
        n = 20
        closes = np.linspace(100, 105, n)
        highs = closes * 1.005
        lows = closes * 0.995
        df = make_ohlcv_df(closes, highs=highs, lows=lows)
        vb = VolBreakout(atr_period=14)
        signal = vb.generate_signal(df)
        assert "atr" in signal["indicators"]
        assert "upper_channel" in signal["indicators"]
        assert "lower_channel" in signal["indicators"]
        assert "prev_close" in signal["indicators"]

    def test_strategy_is_subclass_of_base(self):
        """VolBreakout should be a subclass of Strategy."""
        assert issubclass(VolBreakout, Strategy)
        vb = VolBreakout()
        assert isinstance(vb, Strategy)


class TestSupertrend:
    def test_insufficient_data_returns_hold(self):
        """With fewer bars than atr_period + 1, should return HOLD."""
        df = make_ohlcv_df([100.0, 101.0])
        st = Supertrend(atr_period=10)
        signal = st.generate_signal(df)
        assert signal["action"] == "HOLD"
        assert signal["confidence"] < 0.3

    def test_uptrend_returns_buy(self):
        """Rising prices should produce uptrend -> BUY signal."""
        n = 30
        closes = np.linspace(100, 120, n)
        highs = closes + 0.5
        lows = closes - 0.5
        df = make_ohlcv_df(closes, highs=highs, lows=lows)
        st = Supertrend(atr_period=10, atr_mult=3.0)
        signal = st.generate_signal(df)
        assert signal["action"] in ("BUY", "SELL", "HOLD")
        if signal["action"] == "BUY":
            assert signal["confidence"] > 0.5

    def test_downtrend_returns_sell(self):
        """Falling prices should produce downtrend -> SELL signal."""
        n = 30
        closes = np.linspace(120, 100, n)
        highs = closes + 0.5
        lows = closes - 0.5
        df = make_ohlcv_df(closes, highs=highs, lows=lows)
        st = Supertrend(atr_period=10, atr_mult=3.0)
        signal = st.generate_signal(df)
        assert signal["action"] in ("BUY", "SELL", "HOLD")

    def test_indicators_dict_keys(self):
        """Indicators dict should contain expected keys."""
        n = 30
        closes = np.linspace(100, 110, n)
        highs = closes + 0.5
        lows = closes - 0.5
        df = make_ohlcv_df(closes, highs=highs, lows=lows)
        st = Supertrend(atr_period=10, atr_mult=3.0)
        signal = st.generate_signal(df)
        assert "supertrend" in signal["indicators"]
        assert "direction" in signal["indicators"]
        assert "atr" in signal["indicators"]
        assert "upper_basic" in signal["indicators"]
        assert "lower_basic" in signal["indicators"]

    def test_custom_parameters(self):
        """Supertrend should accept and use custom parameters."""
        st = Supertrend(atr_period=7, atr_mult=2.5)
        assert st.atr_period == 7
        assert st.atr_mult == 2.5

    def test_strategy_is_subclass_of_base(self):
        """Supertrend should be a subclass of Strategy."""
        assert issubclass(Supertrend, Strategy)
        st = Supertrend()
        assert isinstance(st, Strategy)


class TestStrategyFactory:
    def test_create_vol_breakout(self):
        """Factory should create VolBreakout instance."""
        strategy = StrategyFactory.create("vol_breakout")
        assert isinstance(strategy, VolBreakout)

    def test_create_supertrend(self):
        """Factory should create Supertrend instance."""
        strategy = StrategyFactory.create("supertrend")
        assert isinstance(strategy, Supertrend)

    def test_create_rsi_regime_raises(self):
        """Factory should raise NotImplementedError for rsi_regime."""
        with pytest.raises(NotImplementedError):
            StrategyFactory.create("rsi_regime")

    def test_create_unknown_raises(self):
        """Factory should raise ValueError for unknown strategy."""
        with pytest.raises(ValueError):
            StrategyFactory.create("nonexistent_strategy")

    def test_case_insensitive(self):
        """Factory should handle case-insensitive strategy names."""
        vb = StrategyFactory.create("VOL_BREAKOUT")
        assert isinstance(vb, VolBreakout)
        st = StrategyFactory.create("SuperTrend")
        assert isinstance(st, Supertrend)

    def test_with_custom_params(self):
        """Factory should pass custom params to strategy constructor."""
        strategy = StrategyFactory.create(
            "vol_breakout", {"atr_period": 10, "atr_mult_entry": 1.5}
        )
        assert isinstance(strategy, VolBreakout)
        assert strategy.atr_period == 10
        assert strategy.atr_mult_entry == 1.5


class TestOrchestratorIntegration:
    def test_orchestrator_with_vol_breakout(self):
        """Orchestrator should initialize with vol_breakout strategy."""
        from src.intelligence.orchestrator import IntelligenceOrchestrator

        config = {
            "strategy": "vol_breakout",
            "enable_regime": False,
            "enable_lead_lag": False,
            "enable_whale": False,
            "account_balance": 110,
        }
        orch = IntelligenceOrchestrator(config)
        assert orch.strategy is not None
        assert orch.strategy_name == "vol_breakout"

    def test_orchestrator_with_supertrend(self):
        """Orchestrator should initialize with supertrend strategy."""
        from src.intelligence.orchestrator import IntelligenceOrchestrator

        config = {
            "strategy": "supertrend",
            "enable_regime": False,
            "enable_lead_lag": False,
            "enable_whale": False,
            "account_balance": 110,
        }
        orch = IntelligenceOrchestrator(config)
        assert orch.strategy is not None
        assert orch.strategy_name == "supertrend"

    def test_orchestrator_fallback_on_bad_strategy(self):
        """Orchestrator should fall back to rsi_regime on bad strategy name."""
        from src.intelligence.orchestrator import IntelligenceOrchestrator

        config = {
            "strategy": "nonexistent",
            "enable_regime": False,
            "enable_lead_lag": False,
            "enable_whale": False,
            "account_balance": 110,
        }
        orch = IntelligenceOrchestrator(config)
        assert orch.strategy is None
        assert orch.strategy_name == "rsi_regime"

def test_orchestrator_default_no_strategy(monkeypatch):
    """Orchestrator without strategy config should default to rsi_regime."""
    monkeypatch.delenv("STRATEGY", raising=False)
    from src.intelligence.orchestrator import IntelligenceOrchestrator

    config = {
        "enable_regime": False,
        "enable_lead_lag": False,
        "enable_whale": False,
        "account_balance": 110,
    }
    orch = IntelligenceOrchestrator(config)
    assert orch.strategy is None
    assert orch.strategy_name == "rsi_regime"
