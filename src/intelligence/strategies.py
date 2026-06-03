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
            # RSI regime strategy is handled elsewhere in the bot
            raise NotImplementedError("RSI regime strategy is not implemented in this module")
        else:
            raise ValueError(f"Unknown strategy: {strategy_name}. Available: vol_breakout, supertrend, rsi_regime")