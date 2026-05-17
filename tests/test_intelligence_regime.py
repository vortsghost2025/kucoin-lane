import pytest
import pandas as pd
import numpy as np
from src.intelligence.regime_detector import RegimeDetector


def make_ohlcv(prices, high_mult=1.02, low_mult=0.98):
    n = len(prices)
    return pd.DataFrame({
        "high": [p * high_mult for p in prices],
        "low": [p * low_mult for p in prices],
        "close": prices,
        "volume": [1000.0] * n,
    })


class TestRegimeDetector:
    @pytest.fixture
    def detector(self):
        return RegimeDetector(
            adx_period=14, atr_period=14,
            adx_trend_threshold=25, atr_high_threshold=0.03,
        )

    def test_init(self, detector):
        assert detector.adx_period == 14
        assert detector.adx_threshold == 25
        assert detector.current_regime is None

    def test_analyze_insufficient_data(self, detector):
        df = make_ohlcv([100.0] * 5)
        result = detector.analyze(df)
        assert result["regime"] == "UNKNOWN"
        assert result["confidence"] == 0.0

    def test_analyze_sufficient_data(self, detector):
        prices = [100.0 + i * 2 for i in range(30)]
        df = make_ohlcv(prices)
        result = detector.analyze(df)
        assert result["regime"] != "UNKNOWN"
        assert "adx" in result
        assert "atr_pct" in result
        assert "recommendation" in result

    def test_default_response(self, detector):
        result = detector._default_response()
        assert result["regime"] == "UNKNOWN"
        assert result["confidence"] == 0.0
        assert result["recommendation"] == "REDUCE_SIZE"

    def test_should_trade_rsi(self, detector):
        data = {"recommendation": "USE_RSI"}
        assert detector.should_trade_rsi(data) is True
        data = {"recommendation": "REDUCE_SIZE"}
        assert detector.should_trade_rsi(data) is True
        data = {"recommendation": "HALT_TRADING"}
        assert detector.should_trade_rsi(data) is False

    def test_should_halt_trading(self, detector):
        data = {"recommendation": "HALT_TRADING"}
        assert detector.should_halt_trading(data) is True
        data = {"recommendation": "USE_RSI"}
        assert detector.should_halt_trading(data) is False

    def test_get_position_multiplier(self, detector):
        assert detector.get_position_multiplier({"recommendation": "HALT_TRADING"}) == 0.0
        assert detector.get_position_multiplier({"recommendation": "REDUCE_SIZE"}) == 0.5
        assert detector.get_position_multiplier({"recommendation": "USE_RSI"}) == 1.0
        assert detector.get_position_multiplier({"recommendation": "USE_TREND"}) == 0.8
        assert detector.get_position_multiplier({"recommendation": "UNKNOWN"}) == 0.5
