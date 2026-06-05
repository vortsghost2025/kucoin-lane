"""
Historical Backtester - Walk-forward backtesting using real OHLCV klines.

Replaces the formula-based fake backtesting with actual historical data.
Strategy: RSI + Regime-filtered mean reversion / trend following.
"""

import logging
import numpy as np
import pandas as pd
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class HistoricalBacktester:
    """Walk-forward backtester using real klines data."""

    def __init__(self, rsi_period: int = 14, adx_trend_threshold: float = 25.0):
        self.rsi_period = rsi_period
        self.adx_trend_threshold = adx_trend_threshold
        self._cache: Dict[str, Dict] = {}

    def backtest_pair(
        self, pair: str, analysis: Dict[str, Any], klines_fetcher=None, exchange_adapter=None,
    ) -> Optional[Dict[str, Any]]:
        """Run historical backtest for a pair.

        Returns None if no data available.
        """
        if klines_fetcher is None or exchange_adapter is None:
            return None

        normalized_pair = pair.replace("-", "/")

        try:
            df = klines_fetcher.fetch_klines(
                exchange_adapter, normalized_pair, interval="1hour", candle_count=200,
            )

            if df is None or df.empty or len(df) < 50:
                logger.info(
                    f"[HISTORICAL_BT] 1hour klines insufficient for {normalized_pair} "
                    f"({len(df) if df is not None else 0} bars), trying 5min fallback"
                )
                df = klines_fetcher.fetch_klines(
                    exchange_adapter, normalized_pair, interval="5min", candle_count=100,
                )

            if df is None or df.empty or len(df) < 50:
                logger.warning(
                    f"[HISTORICAL_BT] Insufficient klines for {normalized_pair} "
                    f"({len(df) if df is not None else 0} bars)"
                )

            if df is None or df.empty or len(df) < 50:
                logger.warning(
                    f"[HISTORICAL_BT] Insufficient klines for {pair} "
                    f"({len(df) if df is not None else 0} bars)"
                )
                return None

            df = self._calculate_rsi(df, self.rsi_period)
            df = self._calculate_adx_proxy(df)
            trades = self._run_walk_forward(df, pair)

            if not trades:
                logger.info(f"[HISTORICAL_BT] No trades generated for {pair}")
                return {
                    "pair": pair,
                    "win_rate": 0.5,
                    "max_drawdown": 0.05,
                    "total_trades": 0,
                    "avg_win_pct": 0.0,
                    "avg_loss_pct": 0.0,
                    "signal_valid": True,
                    "validation_reason": "No historical trades generated — using neutral estimates",
                    "confidence": 0.5,
                    "recommendation": "PROCEED",
                    "data_source": "klines_empty",
                }

            metrics = self._compute_metrics(trades)
            metrics["pair"] = pair
            metrics["data_source"] = "klines_historical"
            metrics["signal_valid"] = (
                metrics["win_rate"] >= 0.35
                and metrics["max_drawdown"] <= 0.20
            )
            metrics["validation_reason"] = (
                "Signal passed historical backtest validation"
                if metrics["signal_valid"]
                else f"Win rate {metrics['win_rate']:.1%} or drawdown "
                     f"{metrics['max_drawdown']:.1%} outside acceptable range"
            )
            metrics["confidence"] = metrics["win_rate"]
            metrics["recommendation"] = "PROCEED" if metrics["signal_valid"] else "SKIP"

            logger.info(
                f"[HISTORICAL_BT] {pair}: {metrics['total_trades']} trades, "
                f"win_rate={metrics['win_rate']:.1%}, "
                f"max_dd={metrics['max_drawdown']:.1%}, "
                f"avg_win={metrics['avg_win_pct']:.2%}, "
                f"avg_loss={metrics['avg_loss_pct']:.2%}"
            )

            return metrics

        except Exception as e:
            logger.warning(f"[HISTORICAL_BT] Failed for {pair}: {e}")
            return None

    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Calculate RSI from close prices."""
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)

        avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()

        rs = avg_gain / avg_loss.replace(0, np.finfo(float).eps)
        df["rsi"] = 100 - (100 / (1 + rs))
        return df

    def _calculate_adx_proxy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate a simple ADX proxy from price data.

        Uses the `ta` library if available, otherwise a simplified
        version based on directional movement.
        """
        try:
            from ta.trend import ADXIndicator

            adx_ind = ADXIndicator(
                high=df["high"],
                low=df["low"],
                close=df["close"],
                window=14,
            )
            df["adx"] = adx_ind.adx()
            df["adx_pos"] = adx_ind.adx_pos()
            df["adx_neg"] = adx_ind.adx_neg()
        except ImportError:
            high_low = df["high"] - df["low"]
            high_close = (df["high"] - df["close"].shift(1)).abs()
            low_close = (df["low"] - df["close"].shift(1)).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()
            atr_pct = (atr / df["close"]) * 100

            sma = df["close"].rolling(20).mean()
            df["adx"] = atr_pct * 10
            df["adx_pos"] = np.where(df["close"] > sma, df["adx"], 0)
            df["adx_neg"] = np.where(df["close"] < sma, df["adx"], 0)

        return df

    def _run_walk_forward(self, df: pd.DataFrame, pair: str) -> list:
        """Walk-forward backtest: RSI + regime filtering."""
        trades = []
        position = None
        warmup = max(self.rsi_period + 1, 20)

        for i in range(warmup, len(df)):
            row = df.iloc[i]
            rsi = row.get("rsi", 50)
            adx = row.get("adx", 20)
            adx_pos = row.get("adx_pos", 0)
            adx_neg = row.get("adx_neg", 0)
            close = row["close"]

            if np.isnan(rsi) or np.isnan(adx):
                continue

            is_trending = adx > self.adx_trend_threshold
            if is_trending and adx_pos > adx_neg * 1.2:
                regime = "TRENDING_UP"
            elif is_trending and adx_neg > adx_pos * 1.2:
                regime = "TRENDING_DOWN"
            elif is_trending:
                regime = "TRENDING_UP"
            else:
                regime = "RANGING"

        if position is None:
            if regime == "TRENDING_UP" and rsi < 40:
                position = {"entry_price": close, "entry_bar": i, "side": "long"}
            elif regime == "RANGING" and rsi < 30:
                position = {"entry_price": close, "entry_bar": i, "side": "long"}
            elif regime == "TRENDING_DOWN" and rsi > 60:
                position = {"entry_price": close, "entry_bar": i, "side": "short"}
            elif regime == "RANGING" and rsi > 70:
                position = {"entry_price": close, "entry_bar": i, "side": "short"}
        else:
            should_exit = False
            exit_reason = ""
            side = position.get("side", "long")

            if side == "long":
                if rsi > 70:
                    should_exit = True
                    exit_reason = "RSI overbought"
                elif regime == "TRENDING_DOWN":
                    should_exit = True
                    exit_reason = "Regime turned bearish"
                elif i - position["entry_bar"] >= 48:
                    should_exit = True
                    exit_reason = "Max hold period"
                elif close < position["entry_price"] * 0.95:
                    should_exit = True
                    exit_reason = "Stop loss hit"
                elif close > position["entry_price"] * 1.10:
                    should_exit = True
                    exit_reason = "Take profit hit"
            else:
                if rsi < 30:
                    should_exit = True
                    exit_reason = "RSI oversold"
                elif regime == "TRENDING_UP":
                    should_exit = True
                    exit_reason = "Regime turned bullish"
                elif i - position["entry_bar"] >= 48:
                    should_exit = True
                    exit_reason = "Max hold period"
                elif close > position["entry_price"] * 1.05:
                    should_exit = True
                    exit_reason = "Stop loss hit"
                elif close < position["entry_price"] * 0.90:
                    should_exit = True
                    exit_reason = "Take profit hit"

            if should_exit:
                if side == "long":
                    pnl_pct = (close - position["entry_price"]) / position["entry_price"]
                else:
                    pnl_pct = (position["entry_price"] - close) / position["entry_price"]
                trades.append({
                    "entry_price": position["entry_price"],
                    "exit_price": close,
                    "pnl_pct": pnl_pct,
                    "exit_reason": exit_reason,
                    "bars_held": i - position["entry_bar"],
                    "regime_at_entry": regime,
                    "side": side,
                })
                position = None

        if position is not None:
            close = df.iloc[-1]["close"]
            pnl_pct = (close - position["entry_price"]) / position["entry_price"]
            trades.append({
                "entry_price": position["entry_price"],
                "exit_price": close,
                "pnl_pct": pnl_pct,
                "exit_reason": "end_of_data",
                "bars_held": len(df) - 1 - position["entry_bar"],
                "regime_at_entry": "UNKNOWN",
            })

        return trades

    def _compute_metrics(self, trades: list) -> Dict[str, Any]:
        """Compute backtest metrics from trade list."""
        pnls = [t["pnl_pct"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        win_rate = len(wins) / len(trades) if trades else 0.5

        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for pnl in pnls:
            equity *= (1 + pnl)
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd

        avg_win = np.mean(wins) if wins else 0.0
        avg_loss = np.mean(losses) if losses else 0.0

        if len(pnls) > 1:
            sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(8760)
        else:
            sharpe = 0.0

        return {
            "win_rate": win_rate,
            "max_drawdown": max_dd,
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "profit_factor": min(
                abs(sum(wins) / sum(abs(l) for l in losses))
                if losses and sum(abs(l) for l in losses) > 0
                else 99.0,
                99.0,
            ),
            "sharpe_approx": round(sharpe, 2),
        }
