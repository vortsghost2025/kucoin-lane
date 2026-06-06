"""
Trading strategy implementations for KuCoin Lane bot.
Contains VolBreakout and Supertrend strategies based on proven backtest results.
"""

import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Compute ATR using numpy EMA smoothing (same as used in run_mega_sweep.py).
    
    Args:
        high: Array of high prices
        low: Array of low prices
        close: Array of close prices
        period: ATR period (default: 14)
        
    Returns:
        Array of ATR values with same length as input arrays
    """
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = np.empty_like(tr)
    atr[:period] = np.nan
    atr[period-1] = np.mean(tr[1:period+1])  # seed with SMA
    k = 2.0 / (period + 1)
    for i in range(period, len(tr)):
        atr[i] = tr[i] * k + atr[i-1] * (1 - k)
    return atr


class Strategy(ABC):
    """Abstract base class for trading strategies."""
    
    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Generate trading signal based on OHLCV data.
        
        Args:
            df: DataFrame with columns ['open', 'high', 'low', 'close', 'volume']
            
        Returns:
            Dictionary with keys:
                - action: 'BUY', 'SELL', or 'HOLD'
                - confidence: float between 0.0 and 1.0
                - reasoning: string explanation
                - indicators: dict of indicator values used
        """
        pass


class VolBreakout(Strategy):
    """
    Volatility Breakout strategy based on ATR channels.
    
    Entry BUY: when price closes above close[-2] + ATR * atr_mult_entry
    Entry SELL: when price closes below close[-2] - ATR * atr_mult_entry
    """
    
    def __init__(self, atr_period: int = 14, atr_mult_entry: float = 1.0, atr_mult_exit: float = 1.5):
        """
        Initialize VolBreakout strategy.
        
        Args:
            atr_period: Period for ATR calculation (default: 14)
            atr_mult_entry: Multiplier for entry channel (default: 1.0)
            atr_mult_exit: Multiplier for exit channel (default: 1.5)
        """
        self.atr_period = atr_period
        self.atr_mult_entry = atr_mult_entry
        self.atr_mult_exit = atr_mult_exit
        
    def generate_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Generate trading signal based on Volatility Breakout logic.
        
        Returns HOLD with low confidence if insufficient data (< atr_period + 2).
        """
        # Check for sufficient data
        if len(df) < self.atr_period + 2:
            return {
                "action": "HOLD",
                "confidence": 0.1,
                "reasoning": f"Insufficient data: need at least {self.atr_period + 2} bars, got {len(df)}",
                "indicators": {}
            }
            
        # Extract price arrays
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        # Calculate ATR
        atr = compute_atr(high, low, close, self.atr_period)
        
        # Get current and previous values
        curr_close = close[-1]
        prev_close = close[-2]
        curr_atr = atr[-1]
        
        # Handle NaN ATR
        if np.isnan(curr_atr):
            return {
                "action": "HOLD",
                "confidence": 0.1,
                "reasoning": "ATR calculation resulted in NaN",
                "indicators": {"atr": curr_atr}
            }
        
        # Calculate channels
        upper_channel = prev_close + (curr_atr * self.atr_mult_entry)
        lower_channel = prev_close - (curr_atr * self.atr_mult_entry)
        
        # Determine signal
        if curr_close > upper_channel:
            action = "BUY"
            confidence = min(0.95, 0.5 + (curr_close - upper_channel) / (curr_atr * self.atr_mult_entry))
            reasoning = f"Price broke above upper channel: {curr_close:.4f} > {upper_channel:.4f}"
        elif curr_close < lower_channel:
            action = "SELL"
            confidence = min(0.95, 0.5 + (lower_channel - curr_close) / (curr_atr * self.atr_mult_entry))
            reasoning = f"Price broke below lower channel: {curr_close:.4f} < {lower_channel:.4f}"
        else:
            action = "HOLD"
            confidence = 0.3
            reasoning = f"Price within channels: {lower_channel:.4f} <= {curr_close:.4f} <= {upper_channel:.4f}"
            
        return {
            "action": action,
            "confidence": float(confidence),
            "reasoning": reasoning,
            "indicators": {
                "atr": float(curr_atr),
                "upper_channel": float(upper_channel),
                "lower_channel": float(lower_channel),
                "prev_close": float(prev_close)
            }
        }


class Supertrend(Strategy):
    """
    Classic Supertrend indicator strategy.
    
    Uses HL2, ATR, and multiplier to determine trend direction.
    BUY when close < Lower Band (uptrend), SELL when close > Upper Band (downtrend).
    """
    
    def __init__(self, atr_period: int = 10, atr_mult: float = 3.0):
        """
        Initialize Supertrend strategy.
        
        Args:
            atr_period: Period for ATR calculation (default: 10)
            atr_mult: Multiplier for ATR bands (default: 3.0)
        """
        self.atr_period = atr_period
        self.atr_mult = atr_mult
        
    def generate_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Generate trading signal based on Supertrend logic.
        
        Returns HOLD with low confidence if insufficient data (< atr_period + 1).
        """
        # Check for sufficient data
        if len(df) < self.atr_period + 1:
            return {
                "action": "HOLD",
                "confidence": 0.1,
                "reasoning": f"Insufficient data: need at least {self.atr_period + 1} bars, got {len(df)}",
                "indicators": {}
            }
            
        # Extract price arrays
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        # Calculate ATR
        atr = compute_atr(high, low, close, self.atr_period)
        
        # Calculate HL2
        hl2 = (high + low) / 2
        
        # Calculate basic bands
        upper_basic = hl2 + (self.atr_mult * atr)
        lower_basic = hl2 - (self.atr_mult * atr)
        
        # Initialize Supertrend arrays
        supertrend = np.full_like(close, np.nan)
        direction = np.full_like(close, np.nan)  # 1 for uptrend, -1 for downtrend
        
        # Seed values
        supertrend[self.atr_period-1] = hl2[self.atr_period-1]
        direction[self.atr_period-1] = 1  # Start with uptrend assumption
        
        # Calculate Supertrend iteratively
        for i in range(self.atr_period, len(close)):
            # Update bands based on previous close
            if close[i-1] > supertrend[i-1]:
                # Previous close was above Supertrend -> uptrend
                upper_basic[i] = min(upper_basic[i], upper_basic[i-1])
                lower_basic[i] = max(lower_basic[i], lower_basic[i-1])
            else:
                # Previous close was below Supertrend -> downtrend
                upper_basic[i] = max(upper_basic[i], upper_basic[i-1])
                lower_basic[i] = min(lower_basic[i], lower_basic[i-1])
                
            # Determine Supertrend value
            if close[i] <= upper_basic[i]:
                supertrend[i] = upper_basic[i]
                direction[i] = -1  # Downtrend
            else:
                supertrend[i] = lower_basic[i]
                direction[i] = 1   # Uptrend
        
        # Get current values
        curr_close = close[-1]
        curr_supertrend = supertrend[-1]
        curr_direction = direction[-1]
        curr_atr = atr[-1]
        
        # Handle NaN values
        if np.isnan(curr_supertrend) or np.isnan(curr_direction):
            return {
                "action": "HOLD",
                "confidence": 0.1,
                "reasoning": "Supertrend calculation resulted in NaN",
                "indicators": {
                    "supertrend": float(curr_supertrend) if not np.isnan(curr_supertrend) else None,
                    "direction": float(curr_direction) if not np.isnan(curr_direction) else None,
                    "atr": float(curr_atr) if not np.isnan(curr_atr) else None
                }
            }
        
        # Determine signal based on trend direction
        if curr_direction == 1:  # Uptrend
            action = "BUY"
            confidence = 0.7
            reasoning = f"Price in uptrend: close ({curr_close:.4f}) > Supertrend ({curr_supertrend:.4f})"
        else:  # Downtrend
            action = "SELL"
            confidence = 0.7
            reasoning = f"Price in downtrend: close ({curr_close:.4f}) < Supertrend ({curr_supertrend:.4f})"
            
        return {
            "action": action,
            "confidence": float(confidence),
            "reasoning": reasoning,
            "indicators": {
                "supertrend": float(curr_supertrend),
                "direction": float(curr_direction),
                "atr": float(curr_atr),
                "upper_basic": float(upper_basic[-1]),
                "lower_basic": float(lower_basic[-1])
            }
        }


class RsiRegime(Strategy):
    """
    RSI + Regime hybrid strategy.

    Uses RSI for mean-reversion signals in ranging markets,
    and trend-following (momentum confirmation) in trending markets.
    Integrates ADX regime classification to switch between modes.

    BUY:  RSI < oversold in RANGING, or RSI recovering + uptrend in TRENDING_UP
    SELL: RSI > overbought in RANGING, or RSI declining + downtrend in TRENDING_DOWN
    HOLD: No clear signal
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        adx_period: int = 14,
        adx_trend_threshold: float = 25.0,
    ):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.adx_period = adx_period
        self.adx_trend_threshold = adx_trend_threshold

    def generate_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
        min_bars = max(self.rsi_period, self.adx_period) + 1
        if len(df) < min_bars:
            return {
                "action": "HOLD",
                "confidence": 0.1,
                "reasoning": f"Insufficient data: need {min_bars} bars, got {len(df)}",
                "indicators": {},
            }

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values

        rsi = self._compute_rsi(close, self.rsi_period)
        adx, adx_pos, adx_neg = self._compute_adx(high, low, close, self.adx_period)

        curr_rsi = rsi[-1]
        curr_adx = adx[-1]
        curr_adx_pos = adx_pos[-1]
        curr_adx_neg = adx_neg[-1]

        if np.isnan(curr_rsi) or np.isnan(curr_adx):
            return {
                "action": "HOLD",
                "confidence": 0.1,
                "reasoning": "RSI or ADX calculation resulted in NaN",
                "indicators": {"rsi": float(curr_rsi) if not np.isnan(curr_rsi) else None},
            }

        is_trending = curr_adx > self.adx_trend_threshold
        direction = "NEUTRAL"
        if curr_adx_pos > curr_adx_neg * 1.2:
            direction = "BULLISH"
        elif curr_adx_neg > curr_adx_pos * 1.2:
            direction = "BEARISH"

        if not is_trending:
            if curr_rsi < self.oversold:
                action = "BUY"
                confidence = min(0.9, 0.5 + (self.oversold - curr_rsi) / self.oversold * 0.4)
                reasoning = (
                    f"RANGING: RSI oversold ({curr_rsi:.1f} < {self.oversold}) "
                    f"ADX={curr_adx:.1f}"
                )
            elif curr_rsi > self.overbought:
                action = "SELL"
                confidence = min(0.9, 0.5 + (curr_rsi - self.overbought) / (100 - self.overbought) * 0.4)
                reasoning = (
                    f"RANGING: RSI overbought ({curr_rsi:.1f} > {self.overbought}) "
                    f"ADX={curr_adx:.1f}"
                )
            else:
                action = "HOLD"
                confidence = 0.3
                reasoning = (
                    f"RANGING: RSI neutral ({curr_rsi:.1f}) ADX={curr_adx:.1f}"
                )
        else:
            if direction == "BULLISH" and curr_rsi > 40 and curr_rsi < 70:
                action = "BUY"
                confidence = min(0.9, 0.5 + (curr_adx / 50) * 0.4)
                reasoning = (
                    f"TRENDING_UP: RSI momentum ({curr_rsi:.1f}) "
                    f"ADX={curr_adx:.1f} DI+={curr_adx_pos:.1f}"
                )
            elif direction == "BEARISH" and curr_rsi < 60 and curr_rsi > 30:
                action = "SELL"
                confidence = min(0.9, 0.5 + (curr_adx / 50) * 0.4)
                reasoning = (
                    f"TRENDING_DOWN: RSI momentum ({curr_rsi:.1f}) "
                    f"ADX={curr_adx:.1f} DI-={curr_adx_neg:.1f}"
                )
            else:
                action = "HOLD"
                confidence = 0.3
                reasoning = (
                    f"TRENDING ({direction}): RSI={curr_rsi:.1f} no clear entry "
                    f"ADX={curr_adx:.1f}"
                )

        return {
            "action": action,
            "confidence": float(confidence),
            "reasoning": reasoning,
            "indicators": {
                "rsi": float(curr_rsi),
                "adx": float(curr_adx),
                "adx_pos": float(curr_adx_pos),
                "adx_neg": float(curr_adx_neg),
                "regime": "TRENDING" if is_trending else "RANGING",
                "direction": direction,
            },
        }

    @staticmethod
    def _compute_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
        delta = np.diff(close, prepend=close[0])
        gain = np.where(delta > 0, delta, 0.0)
        loss = np.where(delta < 0, -delta, 0.0)
        avg_gain = np.empty_like(close)
        avg_loss = np.empty_like(close)
        avg_gain[:period] = np.nan
        avg_loss[:period] = np.nan
        avg_gain[period] = np.mean(gain[1:period + 1])
        avg_loss[period] = np.mean(loss[1:period + 1])
        k = 2.0 / (period + 1)
        for i in range(period + 1, len(close)):
            avg_gain[i] = gain[i] * k + avg_gain[i - 1] * (1 - k)
            avg_loss[i] = loss[i] * k + avg_loss[i - 1] * (1 - k)
        rs = avg_gain / np.where(avg_loss == 0, 1e-10, avg_loss)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi[:period] = np.nan
        return rsi

    @staticmethod
    def _compute_adx(
        high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14
    ) -> tuple:
        prev_high = np.roll(high, 1)
        prev_low = np.roll(low, 1)
        prev_close = np.roll(close, 1)
        prev_high[0] = high[0]
        prev_low[0] = low[0]
        prev_close[0] = close[0]

        plus_dm = np.maximum(high - prev_high, 0.0)
        minus_dm = np.maximum(prev_low - low, 0.0)
        plus_dm = np.where((high - prev_high) > (prev_low - low), plus_dm, 0.0)
        minus_dm = np.where((prev_low - low) > (high - prev_high), minus_dm, 0.0)

        prev_close_safe = np.where(prev_close == 0, 1e-10, prev_close)
        tr = np.maximum(
            high - low,
            np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)),
        )
        atr = np.empty_like(tr)
        atr[:period] = np.nan
        atr[period - 1] = np.mean(tr[1:period + 1])
        k = 2.0 / (period + 1)
        for i in range(period, len(tr)):
            atr[i] = tr[i] * k + atr[i - 1] * (1 - k)

        smooth_plus_dm = np.empty_like(plus_dm)
        smooth_minus_dm = np.empty_like(minus_dm)
        smooth_plus_dm[:period] = np.nan
        smooth_minus_dm[:period] = np.nan
        smooth_plus_dm[period - 1] = np.sum(plus_dm[1:period + 1])
        smooth_minus_dm[period - 1] = np.sum(minus_dm[1:period + 1])
        for i in range(period, len(close)):
            smooth_plus_dm[i] = plus_dm[i] * k + smooth_plus_dm[i - 1] * (1 - k)
            smooth_minus_dm[i] = minus_dm[i] * k + smooth_minus_dm[i - 1] * (1 - k)

        atr_safe = np.where(atr == 0, 1e-10, atr)
        di_pos = (smooth_plus_dm / atr_safe) * 100.0
        di_neg = (smooth_minus_dm / atr_safe) * 100.0

        dx = np.abs(di_pos - di_neg) / np.where(
            (di_pos + di_neg) == 0, 1e-10, (di_pos + di_neg)
        ) * 100.0
        adx = np.empty_like(dx)
        adx[:period * 2 - 1] = np.nan
        if len(dx) > period * 2 - 1:
            adx[period * 2 - 1] = np.mean(dx[period:period * 2])
            for i in range(period * 2, len(dx)):
                adx[i] = dx[i] * k + adx[i - 1] * (1 - k)

        return adx, di_pos, di_neg


class StrategyFactory:
    """Factory for creating strategy instances."""
    
    @classmethod
    def create(cls, strategy_name: str, params: Optional[Dict[str, Any]] = None) -> Strategy:
        """
        Create a strategy instance by name.
        
        Args:
            strategy_name: Name of strategy ("vol_breakout", "supertrend", "rsi_regime")
            params: Optional parameters for strategy initialization
            
        Returns:
            Strategy instance
            
        Raises:
            ValueError: If strategy_name is not recognized
        """
        if params is None:
            params = {}
            
        strategy_name = strategy_name.lower()
        
        if strategy_name == "vol_breakout":
            return VolBreakout(**params)
        elif strategy_name == "supertrend":
            return Supertrend(**params)
        elif strategy_name == "rsi_regime":
            return RsiRegime(**params)
        else:
            raise ValueError(f"Unknown strategy: {strategy_name}. Available: vol_breakout, supertrend, rsi_regime")