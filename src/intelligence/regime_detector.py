"""
Regime Detector - The Analyst Module
=====================================
Determines if market is TRENDING or RANGING using ADX + ATR.

Logic:
- ADX > 25: Strong Trend -> Disable mean reversion, enable trend following
- ADX < 25: Ranging -> Enable RSI/Bollinger strategies
- ATR: Measures volatility to adjust position sizing
"""

import logging

import numpy as np
import pandas as pd
from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange
from typing import Dict

logger = logging.getLogger(__name__)


class RegimeDetector:
    """
    Market Regime Classification Engine

    Uses ADX (Directional Movement) + ATR (Volatility) to classify:
    - TRENDING_UP: Strong uptrend, use momentum strategies
    - TRENDING_DOWN: Strong downtrend, AVOID longs or use shorts
    - RANGING_HIGH_VOL: Choppy but volatile, reduce position size
    - RANGING_LOW_VOL: Stable range, ideal for mean reversion
    """

    def __init__(
        self,
        adx_period: int = 14,
        atr_period: int = 14,
        adx_trend_threshold: int = 25,
        atr_high_threshold: float = 0.03,
    ):
        self.adx_period = adx_period
        self.atr_period = atr_period
        self.adx_threshold = adx_trend_threshold
        self.atr_high = atr_high_threshold

        self.current_regime = None
        self.regime_confidence = 0.0
        self.last_update = None

    def analyze(self, df: pd.DataFrame) -> Dict:
        """
        Analyze market data and return regime classification.

        Args:
            df: OHLCV DataFrame with high, low, close columns

        Returns:
            {
                "regime": "TRENDING_UP" | "TRENDING_DOWN" | "RANGING_HIGH_VOL" | "RANGING_LOW_VOL",
                "confidence": 0.0-1.0,
                "adx": float,
                "atr_pct": float,
                "directional_trend": "BULLISH" | "BEARISH" | "NEUTRAL",
                "recommendation": "USE_RSI" | "USE_TREND" | "REDUCE_SIZE" | "HALT_TRADING"
            }
        """
        if len(df) < max(self.adx_period, self.atr_period) + 1:
            logger.warning("Insufficient data for regime detection")
            return self._default_response()

        try:
            adx_indicator = ADXIndicator(
                high=df["high"],
                low=df["low"],
                close=df["close"],
                window=self.adx_period,
            )
            adx = adx_indicator.adx().iloc[-1]
            adx_pos = adx_indicator.adx_pos().iloc[-1]
            adx_neg = adx_indicator.adx_neg().iloc[-1]

            atr_indicator = AverageTrueRange(
                high=df["high"],
                low=df["low"],
                close=df["close"],
                window=self.atr_period,
            )
            atr = atr_indicator.average_true_range().iloc[-1]
            atr_pct = (atr / df["close"].iloc[-1]) * 100

            if adx_pos > adx_neg * 1.2:
                direction = "BULLISH"
            elif adx_neg > adx_pos * 1.2:
                direction = "BEARISH"
            else:
                direction = "NEUTRAL"

            is_trending = adx > self.adx_threshold
            is_high_vol = atr_pct > self.atr_high

            if is_trending and direction == "BULLISH":
                regime = "TRENDING_UP"
                recommendation = "USE_TREND"
                confidence = min(adx / 40, 1.0)
            elif is_trending and direction == "BEARISH":
                regime = "TRENDING_DOWN"
                recommendation = "HALT_TRADING"
                confidence = min(adx / 40, 1.0)
            elif not is_trending and is_high_vol:
                regime = "RANGING_HIGH_VOL"
                recommendation = "REDUCE_SIZE"
                confidence = 0.5
            else:
                regime = "RANGING_LOW_VOL"
                recommendation = "USE_RSI"
                confidence = 0.8

            result = {
                "regime": regime,
                "confidence": confidence,
                "adx": round(adx, 2),
                "atr_pct": round(atr_pct, 2),
                "directional_trend": direction,
                "recommendation": recommendation,
                "adx_pos": round(adx_pos, 2),
                "adx_neg": round(adx_neg, 2),
            }

            self.current_regime = regime
            self.regime_confidence = confidence

            logger.info(
                f"Regime: {regime} ({confidence:.1%} confidence) | "
                f"ADX: {adx:.1f} | ATR: {atr_pct:.2f}% | {direction}"
            )

            return result

        except Exception as e:
            logger.error(f"Regime detection failed: {e}")
            return self._default_response()

    def should_trade_rsi(self, regime_data: Dict) -> bool:
        return regime_data["recommendation"] in ["USE_RSI", "REDUCE_SIZE"]

    def should_halt_trading(self, regime_data: Dict) -> bool:
        return regime_data["recommendation"] == "HALT_TRADING"

    def get_position_multiplier(self, regime_data: Dict) -> float:
        """
        Get position size multiplier based on regime.

        Returns:
            1.0 = Normal size
            0.5 = Reduced size (high volatility)
            0.0 = No trading (strong downtrend)
        """
        rec = regime_data["recommendation"]

        if rec == "HALT_TRADING":
            return 0.0
        elif rec == "REDUCE_SIZE":
            return 0.5
        elif rec == "USE_RSI":
            return 1.0
        elif rec == "USE_TREND":
            return 0.8
        else:
            return 0.5

    def _default_response(self) -> Dict:
        return {
            "regime": "UNKNOWN",
            "confidence": 0.0,
            "adx": 0.0,
            "atr_pct": 0.0,
            "directional_trend": "NEUTRAL",
            "recommendation": "REDUCE_SIZE",
        }
