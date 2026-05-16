"""
Whale Watch - The Hunter Module
================================
Tracks order flow imbalance and liquidation levels to find "Smart Money" footprints.

The Secret: Prices move because of LIQUIDATIONS, not "oversold RSI."
The Edge: Buy when whales are absorbing (CVD rising while price falls).

Monitors:
- Cumulative Volume Delta (Buy Volume - Sell Volume)
- Order Book Imbalance (Bid/Ask pressure)
- Funding Rate (Short Squeeze indicator)
"""

import logging
from datetime import datetime
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class WhaleWatch:
    """
    Order Flow and Liquidation Tracker

    Detects:
    - BULLISH_ABSORPTION: Price falling but whales buying (CVD positive)
    - BEARISH_DISTRIBUTION: Price rising but whales selling (CVD negative)
    - SQUEEZE_SETUP: Extreme funding rates indicate pending liquidations
    """

    def __init__(
        self,
        cvd_threshold: float = 0.6,
        imbalance_threshold: float = 1.5,
    ):
        self.cvd_threshold = cvd_threshold
        self.imbalance_threshold = imbalance_threshold

        self.current_signal = "NEUTRAL"
        self.confidence = 0.0

    def analyze_order_flow(
        self, df: pd.DataFrame, order_book: Optional[Dict] = None
    ) -> Dict:
        """
        Analyze order flow for whale activity.

        Args:
            df: OHLCV with 'buy_volume' and 'sell_volume' columns
            order_book: Optional order book data {bids: float, asks: float}

        Returns:
            {
                "signal": "BULLISH_ABSORPTION" | "BEARISH_DISTRIBUTION" | "NEUTRAL",
                "confidence": 0.0-1.0,
                "cvd_ratio": float (% buy volume),
                "order_imbalance": float (bid/ask ratio),
                "recommendation": str
            }
        """
        try:
            if "buy_volume" in df.columns and "sell_volume" in df.columns:
                buy_vol = df["buy_volume"].tail(20).sum()
                sell_vol = df["sell_volume"].tail(20).sum()
                total_vol = buy_vol + sell_vol

                cvd_ratio = buy_vol / total_vol if total_vol > 0 else 0.5
            else:
                cvd_ratio = self._estimate_cvd_from_price(df)

            price_change = (df["close"].iloc[-1] - df["close"].iloc[-20]) / df[
                "close"
            ].iloc[-20]

            book_imbalance = 1.0
            if order_book:
                bids = order_book.get("bids", 0)
                asks = order_book.get("asks", 0)
                book_imbalance = bids / asks if asks > 0 else 1.0

            signal, confidence, recommendation = self._classify_flow(
                cvd_ratio, price_change, book_imbalance
            )

            result = {
                "signal": signal,
                "confidence": confidence,
                "cvd_ratio": round(cvd_ratio, 3),
                "price_change_pct": round(price_change * 100, 2),
                "order_imbalance": round(book_imbalance, 2),
                "recommendation": recommendation,
            }

            self.current_signal = signal
            self.confidence = confidence

            logger.info(
                f"Whale Watch: {signal} ({confidence:.1%}) | "
                f"CVD: {cvd_ratio:.1%} | Price: {price_change * 100:+.2f}%"
            )

            return result

        except Exception as e:
            logger.error(f"Order flow analysis failed: {e}")
            return self._default_response()

    def _classify_flow(
        self, cvd_ratio: float, price_change: float, book_imbalance: float
    ) -> tuple[str, float, str]:
        """
        Classify order flow into actionable signals.

        Returns:
            (signal, confidence, recommendation)
        """
        if price_change < -0.01 and cvd_ratio > self.cvd_threshold:
            confidence = min(cvd_ratio + abs(price_change), 1.0)
            return (
                "BULLISH_ABSORPTION",
                confidence,
                "STRONG_BUY - Whales accumulating the dip",
            )

        elif price_change > 0.01 and cvd_ratio < (1 - self.cvd_threshold):
            confidence = min((1 - cvd_ratio) + price_change, 1.0)
            return (
                "BEARISH_DISTRIBUTION",
                confidence,
                "EXIT - Whales distributing into strength",
            )

        elif book_imbalance > self.imbalance_threshold:
            return ("SQUEEZE_SETUP", 0.7, "PREPARE - Liquidation cascade possible")

        elif cvd_ratio > 0.55:
            return ("WEAK_ACCUMULATION", 0.4, "WATCH - Some buying but not strong")

        else:
            return ("NEUTRAL", 0.3, "NO_ACTION - Balanced flow")

    def _estimate_cvd_from_price(self, df: pd.DataFrame) -> float:
        """
        Estimate CVD from price action when volume breakdown unavailable.

        Logic: Up candles = buy pressure, down candles = sell pressure
        """
        recent = df.tail(20).copy()
        recent["direction"] = (recent["close"] > recent["open"]).astype(int)

        buy_weighted = recent[recent["direction"] == 1]["volume"].sum()
        total_vol = recent["volume"].sum()

        return buy_weighted / total_vol if total_vol > 0 else 0.5

    def should_buy(self, flow_data: Dict) -> bool:
        return (
            flow_data["signal"] == "BULLISH_ABSORPTION"
            and flow_data["confidence"] > 0.6
        )

    def should_exit(self, flow_data: Dict) -> bool:
        return (
            flow_data["signal"] == "BEARISH_DISTRIBUTION"
            and flow_data["confidence"] > 0.6
        )

    def _default_response(self) -> Dict:
        return {
            "signal": "NEUTRAL",
            "confidence": 0.0,
            "cvd_ratio": 0.5,
            "price_change_pct": 0.0,
            "order_imbalance": 1.0,
            "recommendation": "ERROR - Analysis failed",
        }
