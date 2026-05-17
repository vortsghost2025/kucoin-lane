import pytest
import pandas as pd
import numpy as np
from src.intelligence.whale_watch import WhaleWatch


class TestWhaleWatch:
    @pytest.fixture
    def ww(self):
        return WhaleWatch(cvd_threshold=0.6, imbalance_threshold=1.5)

    def make_df(self, prices, buy_vol=None, sell_vol=None):
        n = len(prices)
        data = {
            "open": [p * 0.99 for p in prices],
            "high": [p * 1.02 for p in prices],
            "low": [p * 0.98 for p in prices],
            "close": prices,
            "volume": [1000.0] * n,
        }
        if buy_vol is not None:
            data["buy_volume"] = buy_vol
        if sell_vol is not None:
            data["sell_volume"] = sell_vol
        return pd.DataFrame(data)

    def test_init(self, ww):
        assert ww.cvd_threshold == 0.6
        assert ww.current_signal == "NEUTRAL"

    def test_bullish_absorption(self, ww):
        df = self.make_df(
            prices=[100.0 * (1 - 0.02 * i) for i in range(20)],
            buy_vol=[2000.0] * 20,
            sell_vol=[500.0] * 20,
        )
        result = ww.analyze_order_flow(df)
        assert result["signal"] == "BULLISH_ABSORPTION"
        assert result["confidence"] > 0.5

    def test_bearish_distribution(self, ww):
        df = self.make_df(
            prices=[100.0 * (1 + 0.02 * i) for i in range(20)],
            buy_vol=[500.0] * 20,
            sell_vol=[2000.0] * 20,
        )
        result = ww.analyze_order_flow(df)
        assert result["signal"] == "BEARISH_DISTRIBUTION"

    def test_neutral_flow(self, ww):
        df = self.make_df(
            prices=[100.0] * 20,
            buy_vol=[1000.0] * 20,
            sell_vol=[1000.0] * 20,
        )
        result = ww.analyze_order_flow(df)
        assert result["signal"] == "WEAK_ACCUMULATION" or result["signal"] == "NEUTRAL"

    def test_estimate_cvd_from_price(self, ww):
        prices = [100, 101, 102, 101, 103, 102]
        df = self.make_df(prices)
        cvd = ww._estimate_cvd_from_price(df)
        assert 0 <= cvd <= 1

    def test_should_buy(self, ww):
        data = {"signal": "BULLISH_ABSORPTION", "confidence": 0.8}
        assert ww.should_buy(data) is True
        data = {"signal": "NEUTRAL", "confidence": 0.8}
        assert ww.should_buy(data) is False

    def test_should_exit(self, ww):
        data = {"signal": "BEARISH_DISTRIBUTION", "confidence": 0.8}
        assert ww.should_exit(data) is True
        data = {"signal": "NEUTRAL", "confidence": 0.8}
        assert ww.should_exit(data) is False

    def test_squeeze_setup(self, ww):
        df = self.make_df(
            prices=[100.0] * 20,
            buy_vol=[1000.0] * 20,
            sell_vol=[1000.0] * 20,
        )
        order_book = {"bids": 200.0, "asks": 100.0}
        result = ww.analyze_order_flow(df, order_book=order_book)
        assert result["signal"] == "SQUEEZE_SETUP"
