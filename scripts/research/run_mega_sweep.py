#!/usr/bin/env python3
"""
Mega multi-strategy backtest sweep — 5 years of BTC/USDT 1h data.

Strategies tested:
  1. RSI Oversold Bounce
  2. Dual EMA Crossover
  3. Bollinger Band Bounce
  4. Supertrend
  5. Regime Switch (ADX + RSI/EMA)
  6. Donchian Channel Breakout
  7. MACD Signal Crossover
  8. Stochastic Oscillator
  9. Volatility Breakout (ATR)
  10. Williams %R

Regime classification per bar: BULL / BEAR / RANGE (ADX + EMA200 slope)
Exit stack: SL → breakeven → trailing → R:R TP → sell signal (gated by MIN_PROFIT_TO_HOLD_PCT)
Spot-long-only, single position, compounding equity, taker fees both sides.

Outputs:
  docs/research/mega_sweep_results.json
  docs/research/MEGA_SWEEP_RESULTS.md

Usage:
  python3 scripts/research/run_mega_sweep.py
  python3 scripts/research/run_mega_sweep.py --strategies rsi,ema_cross,bb
  python3 scripts/research/run_mega_sweep.py --start-equity 110 --top 10
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, field
from itertools import product
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Iterable

import numpy as np

# =========================================================================== #
# Data loading
# =========================================================================== #
def load_csv(path: Path) -> dict[str, np.ndarray]:
    rows = list(csv.DictReader(path.open()))
    return {
        "ts": np.array([int(r["ts"]) for r in rows], dtype=np.int64),
        "open": np.array([float(r["open"]) for r in rows]),
        "high": np.array([float(r["high"]) for r in rows]),
        "low": np.array([float(r["low"]) for r in rows]),
        "close": np.array([float(r["close"]) for r in rows]),
        "volume": np.array([float(r["volume"]) for r in rows]),
    }


# =========================================================================== #
# Core indicators (numpy only)
# =========================================================================== #
def ema(arr: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1)
    out = np.empty_like(arr)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def sma(arr: np.ndarray, period: int) -> np.ndarray:
    out = np.empty_like(arr)
    out[:period] = arr[:period]
    for i in range(period - 1, len(arr)):
        out[i] = arr[i - period + 1:i + 1].mean()
    return out


def wilder_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.empty_like(close)
    avg_loss = np.empty_like(close)
    avg_gain[:period] = gain[:period].mean()
    avg_loss[:period] = loss[:period].mean()
    for i in range(period, len(close)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period
    rs = np.where(avg_loss == 0, 0.0, avg_gain / np.maximum(avg_loss, 1e-12))
    rsi = np.where(avg_loss == 0, 100.0, 100.0 - (100.0 / (1.0 + rs)))
    return rsi


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    out = np.empty_like(tr)
    out[:period] = tr[:period].mean()
    for i in range(period, len(tr)):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (adx_val, plus_di, minus_di)."""
    delta_high = high - np.roll(high, 1)
    delta_low = np.roll(low, 1) - low
    delta_high[0] = 0
    delta_low[0] = 0
    plus_dm = np.where((delta_high > delta_low) & (delta_high > 0), delta_high, 0.0)
    minus_dm = np.where((delta_low > delta_high) & (delta_low > 0), delta_low, 0.0)
    tr = np.maximum(high - low, np.maximum(np.abs(high - np.roll(close, 1)), np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    atr_val = np.empty_like(tr)
    atr_val[:period] = tr[:period].mean()
    for i in range(period, len(tr)):
        atr_val[i] = (atr_val[i - 1] * (period - 1) + tr[i]) / period
    smooth_plus = np.empty_like(tr)
    smooth_minus = np.empty_like(tr)
    smooth_plus[:period] = plus_dm[:period].sum()
    smooth_minus[:period] = minus_dm[:period].sum()
    for i in range(period, len(tr)):
        smooth_plus[i] = smooth_plus[i - 1] - smooth_plus[i - 1] / period + plus_dm[i]
        smooth_minus[i] = smooth_minus[i - 1] - smooth_minus[i - 1] / period + minus_dm[i]
    plus_di = np.where(atr_val > 0, smooth_plus / atr_val * 100, 0.0)
    minus_di = np.where(atr_val > 0, smooth_minus / atr_val * 100, 0.0)
    dx = np.where((plus_di + minus_di) > 0, np.abs(plus_di - minus_di) / (plus_di + minus_di) * 100, 0.0)
    adx_val = np.empty_like(dx)
    adx_val[:period * 2] = dx[:period * 2].mean()
    for i in range(period * 2, len(dx)):
        adx_val[i] = (adx_val[i - 1] * (period - 1) + dx[i]) / period
    return adx_val, plus_di, minus_di


def bollinger_bands(close: np.ndarray, period: int = 20, num_std: float = 2.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    mid = sma(close, period)
    # rolling std
    std = np.empty_like(close)
    std[:period] = 0
    for i in range(period - 1, len(close)):
        std[i] = close[i - period + 1:i + 1].std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def supertrend(high: np.ndarray, low: np.ndarray, close: np.ndarray,
               atr_period: int = 10, atr_mult: float = 3.0) -> Tuple[np.ndarray, np.ndarray]:
    """Returns (supertrend_value, direction) where direction=1 bullish, -1 bearish."""
    atr_val = atr(high, low, close, atr_period)
    hl2 = (high + low) / 2.0
    n = len(close)
    upper_band = hl2 + atr_mult * atr_val
    lower_band = hl2 - atr_mult * atr_val
    # Final bands with overlap logic
    final_upper = np.empty_like(close)
    final_lower = np.empty_like(close)
    direction = np.ones(n, dtype=np.int8)  # 1 = bullish
    st_val = np.empty_like(close)
    final_upper[0] = upper_band[0]
    final_lower[0] = lower_band[0]
    direction[0] = 1
    st_val[0] = lower_band[0]
    for i in range(1, n):
        # lower band: can only go up (or stay)
        if lower_band[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
            final_lower[i] = lower_band[i]
        else:
            final_lower[i] = final_lower[i - 1]
        # upper band: can only go down (or stay)
        if upper_band[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
            final_upper[i] = upper_band[i]
        else:
            final_upper[i] = final_upper[i - 1]
        # direction
        if direction[i - 1] == 1:
            if close[i] < final_lower[i]:
                direction[i] = -1
            else:
                direction[i] = 1
        else:
            if close[i] > final_upper[i]:
                direction[i] = 1
            else:
                direction[i] = -1
        st_val[i] = final_lower[i] if direction[i] == 1 else final_upper[i]
    return st_val, direction


def stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray,
               k_period: int = 14, d_period: int = 3) -> Tuple[np.ndarray, np.ndarray]:
    n = len(close)
    pct_k = np.empty(n)
    for i in range(k_period - 1, n):
        hh = high[i - k_period + 1:i + 1].max()
        ll = low[i - k_period + 1:i + 1].min()
        pct_k[i] = (close[i] - ll) / (hh - ll) * 100.0 if hh != ll else 50.0
    pct_k[:k_period - 1] = 50.0
    pct_d = sma(pct_k, d_period)
    return pct_k, pct_d


def donchian_channel(high: np.ndarray, low: np.ndarray, period: int = 20) -> Tuple[np.ndarray, np.ndarray]:
    n = len(high)
    upper = np.empty(n)
    lower = np.empty(n)
    for i in range(period - 1, n):
        upper[i] = high[i - period + 1:i + 1].max()
        lower[i] = low[i - period + 1:i + 1].min()
    upper[:period - 1] = high[:period - 1]
    lower[:period - 1] = low[:period - 1]
    return upper, lower


def williams_pct_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    out = np.empty(n)
    for i in range(period - 1, n):
        hh = high[i - period + 1:i + 1].max()
        ll = low[i - period + 1:i + 1].min()
        out[i] = (hh - close[i]) / (hh - ll) * -100.0 if hh != ll else -50.0
    out[:period - 1] = -50.0
    return out


def ema_slope(ema_arr: np.ndarray, lookback: int = 20) -> np.ndarray:
    """Linear regression slope of last `lookback` values at each point."""
    n = len(ema_arr)
    slope = np.zeros(n)
    x = np.arange(lookback, dtype=float)
    x_mean = x.mean()
    x_var = ((x - x_mean) ** 2).sum()
    for i in range(lookback - 1, n):
        y = ema_arr[i - lookback + 1:i + 1]
        y_mean = y.mean()
        slope[i] = ((x - x_mean) * (y - y_mean)).sum() / x_var if x_var > 0 else 0.0
    return slope


# =========================================================================== #
# Regime classification
# =========================================================================== #
def classify_regime(close: np.ndarray, ema200: np.ndarray) -> np.ndarray:
    """
    0=RANGE, 1=BULL, -1=BEAR
    BULL: close > ema200 AND ema200 slope > 0
    BEAR: close < ema200 AND ema200 slope < 0
    RANGE: else
    """
    slope = ema_slope(ema200, 20)
    regime = np.zeros(len(close), dtype=np.int8)
    regime[(close > ema200) & (slope > 0)] = 1   # BULL
    regime[(close < ema200) & (slope < 0)] = -1   # BEAR
    # rest = RANGE (0)
    return regime


# =========================================================================== #
# Signal builders per strategy
# =========================================================================== #

def signals_rsi(close, rsi, ema_slow, rsi_buy, rsi_sell, require_trend):
    rsi_prev = np.empty_like(rsi)
    rsi_prev[0] = rsi[0]
    rsi_prev[1:] = rsi[:-1]
    buy = (rsi_prev < rsi_buy) & (rsi >= rsi_buy)
    if require_trend:
        buy = buy & (close > ema_slow)
    sell = (rsi_prev > rsi_sell) & (rsi <= rsi_sell)
    return buy, sell


def signals_ema_cross(ema_fast, ema_slow):
    diff = ema_fast - ema_slow
    prev_diff = np.empty_like(diff)
    prev_diff[0] = 0.0
    prev_diff[1:] = diff[:-1]
    buy = (prev_diff <= 0) & (diff > 0)
    sell = (prev_diff >= 0) & (diff < 0)
    return buy, sell


def signals_bb(close, bb_upper, bb_lower):
    prev_below = np.empty(len(close), dtype=bool)
    prev_below[0] = False
    prev_below[1:] = close[:-1] < bb_lower[:-1]
    curr_above = close > bb_lower
    buy = prev_below & curr_above
    sell = close >= bb_upper
    return buy, sell


def signals_supertrend(direction):
    prev_dir = np.empty_like(direction)
    prev_dir[0] = direction[0]
    prev_dir[1:] = direction[:-1]
    buy = (prev_dir == -1) & (direction == 1)
    sell = (prev_dir == 1) & (direction == -1)
    return buy, sell


def signals_regime_switch(close, rsi, ema_fast, ema_slow, adx_val, plus_di, minus_di, adx_thresh, rsi_buy, rsi_sell):
    """ADX > thresh: EMA cross entry. ADX < thresh: RSI oversold entry."""
    # EMA cross signals
    ema_buy, ema_sell = signals_ema_cross(ema_fast, ema_slow)
    # RSI signals (no trend filter for regime switch range mode)
    rsi_buy_sig, rsi_sell_sig = signals_rsi(close, rsi, ema_slow, rsi_buy, rsi_sell, False)
    # Merge based on ADX
    trending = adx_val > adx_thresh
    buy = np.where(trending, ema_buy, rsi_buy_sig)
    sell = np.where(trending, ema_sell, rsi_sell_sig)
    return buy, sell


def signals_donchian(close, dc_upper, dc_lower):
    prev_close = np.empty_like(close)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]
    buy = (close > dc_upper) & (prev_close <= dc_upper)
    sell = (close < dc_lower) & (prev_close >= dc_lower)
    return buy, sell


def signals_macd(macd_line, signal_line):
    diff = macd_line - signal_line
    prev_diff = np.empty_like(diff)
    prev_diff[0] = 0.0
    prev_diff[1:] = diff[:-1]
    buy = (prev_diff <= 0) & (diff > 0)
    sell = (prev_diff >= 0) & (diff < 0)
    return buy, sell


def signals_stochastic(pct_k, pct_d, oversold=20, overbought=80):
    prev_k = np.empty_like(pct_k)
    prev_k[0] = pct_k[0]
    prev_k[1:] = pct_k[:-1]
    prev_d = np.empty_like(pct_d)
    prev_d[0] = pct_d[0]
    prev_d[1:] = pct_d[:-1]
    buy = (prev_k < prev_d) & (pct_k >= pct_d) & (pct_k < oversold)
    sell = (prev_k > prev_d) & (pct_k <= pct_d) & (pct_k > overbought)
    return buy, sell


def signals_vol_breakout(close, atr_val, atr_mult_entry):
    """Entry: close > prev_close + atr_mult * ATR."""
    prev_close = np.empty_like(close)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]
    threshold = prev_close + atr_mult_entry * atr_val
    buy = close > threshold
    # No explicit sell signal; rely on trailing stop and max-bars exit
    sell = np.zeros(len(close), dtype=bool)
    return buy, sell


def signals_williams(pct_r, oversold=-80, overbought=-20):
    prev = np.empty_like(pct_r)
    prev[0] = pct_r[0]
    prev[1:] = pct_r[:-1]
    buy = (prev < oversold) & (pct_r >= oversold)
    sell = (prev > overbought) & (pct_r <= overbought)
    return buy, sell


# =========================================================================== #
# Simulation engine (shared across all strategies)
# =========================================================================== #
@dataclass
class Result:
    strategy: str
    # common params
    risk_pct: float
    stop_loss_pct: float
    rr: float
    trail_activate_pct: float
    trail_pct: float
    breakeven_activate_pct: float
    min_profit_hold_pct: float
    # strategy-specific params (as json string)
    strategy_params: str
    # outcomes
    trades: int
    wins: int
    win_rate: float
    final_equity: float
    net_return_pct: float
    max_drawdown_pct: float
    profit_factor: float
    avg_win_pct: float
    avg_loss_pct: float
    sharpe_like: float
    # regime breakdown
    bull_trades: int
    bear_trades: int
    range_trades: int
    bull_pnl_pct: float
    bear_pnl_pct: float
    range_pnl_pct: float
    # meta
    days: float


def simulate(
    bars: dict[str, np.ndarray],
    buy: np.ndarray,
    sell: np.ndarray,
    regime: np.ndarray,
    start_equity: float,
    risk_pct: float,
    stop_loss_pct: float,
    rr: float,
    trail_activate_pct: float,
    trail_pct: float,
    breakeven_activate_pct: float,
    min_profit_hold_pct: float,
    fee_pct: float,
    micro_account_threshold: float,
    confidence_floor: float,
    asset_multiplier: float,
    min_notional: float,
    warmup: int,
    max_bars_in_trade: int = 0,  # 0 = disabled
) -> Tuple[List[float], List[float], List[bool], float, dict]:
    """Returns (trade_returns_pct, equity_curve, win_flags, max_dd, regime_stats)."""
    high = bars["high"]
    low = bars["low"]
    close = bars["close"]
    n = len(close)

    equity = start_equity
    peak_equity = start_equity
    max_dd = 0.0
    equity_curve = [equity]
    trade_returns: list[float] = []
    win_flags: list[bool] = []

    # regime tracking
    regime_pnl = {1: 0.0, -1: 0.0, 0: 0.0}
    regime_trades = {1: 0, -1: 0, 0: 0}

    # position state
    in_pos = False
    entry_price = 0.0
    qty = 0.0
    stop = 0.0
    take = 0.0
    trail_armed = False
    breakeven_done = False
    peak_in_trade = 0.0
    entry_bar = 0
    entry_regime = 0

    for i in range(warmup, n):
        h, l, c = high[i], low[i], close[i]

        if in_pos:
            peak_in_trade = max(peak_in_trade, h)

            # breakeven move
            if not breakeven_done:
                if (peak_in_trade / entry_price - 1.0) * 100.0 >= breakeven_activate_pct:
                    stop = max(stop, entry_price * (1.0 + fee_pct * 2))
                    breakeven_done = True

            # trailing arm + ratchet
            if not trail_armed:
                if (peak_in_trade / entry_price - 1.0) * 100.0 >= trail_activate_pct:
                    trail_armed = True
            if trail_armed:
                new_stop = peak_in_trade * (1.0 - trail_pct / 100.0)
                stop = max(stop, new_stop)

            # exit checks in priority order
            exit_price = None
            exit_reason = ""

            # adverse first (stop checked before TP in same bar)
            if l <= stop:
                exit_price = stop
                exit_reason = "stop"
            elif h >= take:
                exit_price = take
                exit_reason = "tp"
            elif sell[i]:
                cur_profit_pct = (c / entry_price - 1.0) * 100.0
                if cur_profit_pct < min_profit_hold_pct:
                    exit_price = c
                    exit_reason = "sell_signal"
            # max bars exit (for vol breakout strategy)
            elif max_bars_in_trade > 0 and (i - entry_bar) >= max_bars_in_trade:
                exit_price = c
                exit_reason = "max_bars"

            if exit_price is not None:
                gross_ret = (exit_price - entry_price) / entry_price
                net_ret = gross_ret - 2 * fee_pct
                pnl = qty * entry_price * net_ret
                equity += pnl
                trade_returns.append(net_ret * 100.0)
                win_flags.append(net_ret > 0)
                regime_pnl[entry_regime] += net_ret * 100.0
                regime_trades[entry_regime] += 1
                in_pos = False
                qty = 0.0
                trail_armed = False
                breakeven_done = False
                peak_in_trade = 0.0
                peak_equity = max(peak_equity, equity)
                dd = (peak_equity - equity) / peak_equity * 100.0
                max_dd = max(max_dd, dd)

        equity_curve.append(equity)

        # new entry (only when flat, no entry on same bar as exit)
        if not in_pos and buy[i]:
            max_risk_amount = equity * risk_pct
            if equity < micro_account_threshold:
                cm = 1.0
            else:
                cm = max(0.5, confidence_floor)
            risk_dollars = max_risk_amount * cm
            risk_per_unit = c * (stop_loss_pct / 100.0)
            if risk_per_unit <= 0:
                continue
            raw_qty = risk_dollars / risk_per_unit
            qty_attempt = raw_qty * asset_multiplier
            notional = qty_attempt * c
            if notional < min_notional:
                continue
            if notional > equity * 0.95:
                qty_attempt = (equity * 0.95) / c

            in_pos = True
            entry_price = c
            qty = qty_attempt
            stop = entry_price * (1.0 - stop_loss_pct / 100.0)
            take = entry_price * (1.0 + (stop_loss_pct * rr) / 100.0)
            peak_in_trade = entry_price
            entry_bar = i
            entry_regime = int(regime[i])

    # close any open position at last close
    if in_pos:
        gross_ret = (close[-1] - entry_price) / entry_price
        net_ret = gross_ret - 2 * fee_pct
        pnl = qty * entry_price * net_ret
        equity += pnl
        trade_returns.append(net_ret * 100.0)
        win_flags.append(net_ret > 0)
        regime_pnl[entry_regime] += net_ret * 100.0
        regime_trades[entry_regime] += 1
        equity_curve[-1] = equity
        peak_equity = max(peak_equity, equity)
        dd = (peak_equity - equity) / peak_equity * 100.0
        max_dd = max(max_dd, dd)

    regime_stats = {
        "bull_trades": regime_trades[1],
        "bear_trades": regime_trades[-1],
        "range_trades": regime_trades[0],
        "bull_pnl_pct": regime_pnl[1],
        "bear_pnl_pct": regime_pnl[-1],
        "range_pnl_pct": regime_pnl[0],
    }
    return trade_returns, equity_curve, win_flags, max_dd, regime_stats


# =========================================================================== #
# Strategy param grids
# =========================================================================== #
ALL_STRATEGIES = ["rsi", "ema_cross", "bb", "supertrend", "regime_switch",
                  "donchian", "macd", "stochastic", "vol_breakout", "williams"]

# Common params shared across all strategies
# Reduced from 11 to 7 risk levels to keep runtime manageable
COMMON_RISK = [0.005, 0.0075, 0.01, 0.02, 0.05, 0.10, 0.50]
COMMON_SL = [1.5, 2.0, 3.0, 5.0]
COMMON_RR = [1.5, 2.0, 3.0]
COMMON_TRAIL_ACT = [1.5, 2.0, 3.0]
COMMON_TRAIL = [1.5]
COMMON_BE_ACT = [1.0]
COMMON_MIN_PROFIT_HOLD = [1.0]


def grid_rsi():
    for risk, sl, rr, ta, tp, ba, mph in product(
        COMMON_RISK, COMMON_SL, COMMON_RR, COMMON_TRAIL_ACT, COMMON_TRAIL, COMMON_BE_ACT, COMMON_MIN_PROFIT_HOLD
    ):
        for rsi_buy, rsi_sell in product([25, 30, 35, 40], [65, 70, 75]):
            for ema_slow, require_trend in product([50, 100], [True, False]):
                yield {
                    "strategy": "rsi",
                    "risk_pct": risk, "stop_loss_pct": sl, "rr": rr,
                    "trail_activate_pct": ta, "trail_pct": tp,
                    "breakeven_activate_pct": ba, "min_profit_hold_pct": mph,
                    "rsi_buy": rsi_buy, "rsi_sell": rsi_sell,
                    "ema_slow": ema_slow, "require_trend": require_trend,
                }


def grid_ema_cross():
    for risk, sl, rr, ta, tp, ba, mph in product(
        COMMON_RISK, COMMON_SL, COMMON_RR, COMMON_TRAIL_ACT, COMMON_TRAIL, COMMON_BE_ACT, COMMON_MIN_PROFIT_HOLD
    ):
        for ema_fast, ema_slow in product([9, 12, 21], [50, 100, 200]):
            yield {
                "strategy": "ema_cross",
                "risk_pct": risk, "stop_loss_pct": sl, "rr": rr,
                "trail_activate_pct": ta, "trail_pct": tp,
                "breakeven_activate_pct": ba, "min_profit_hold_pct": mph,
                "ema_fast": ema_fast, "ema_slow": ema_slow,
            }


def grid_bb():
    for risk, sl, rr, ta, tp, ba, mph in product(
        COMMON_RISK, COMMON_SL, COMMON_RR, COMMON_TRAIL_ACT, COMMON_TRAIL, COMMON_BE_ACT, COMMON_MIN_PROFIT_HOLD
    ):
        for bb_std in [2.0, 2.5, 3.0]:
            yield {
                "strategy": "bb",
                "risk_pct": risk, "stop_loss_pct": sl, "rr": rr,
                "trail_activate_pct": ta, "trail_pct": tp,
                "breakeven_activate_pct": ba, "min_profit_hold_pct": mph,
                "bb_period": 20, "bb_std": bb_std,
            }


def grid_supertrend():
    for risk, sl, rr, ta, tp, ba, mph in product(
        COMMON_RISK, COMMON_SL, COMMON_RR, COMMON_TRAIL_ACT, COMMON_TRAIL, COMMON_BE_ACT, COMMON_MIN_PROFIT_HOLD
    ):
        for atr_period, atr_mult in product([10, 14], [2.0, 2.5, 3.0, 3.5]):
            yield {
                "strategy": "supertrend",
                "risk_pct": risk, "stop_loss_pct": sl, "rr": rr,
                "trail_activate_pct": ta, "trail_pct": tp,
                "breakeven_activate_pct": ba, "min_profit_hold_pct": mph,
                "atr_period": atr_period, "atr_mult": atr_mult,
            }


def grid_regime_switch():
    for risk, sl, rr, ta, tp, ba, mph in product(
        COMMON_RISK, COMMON_SL, COMMON_RR, COMMON_TRAIL_ACT, COMMON_TRAIL, COMMON_BE_ACT, COMMON_MIN_PROFIT_HOLD
    ):
        for adx_thresh, rsi_buy in product([20, 25, 30], [30, 35, 40]):
            for ema_fast, ema_slow in product([9, 21], [50, 100]):
                yield {
                    "strategy": "regime_switch",
                    "risk_pct": risk, "stop_loss_pct": sl, "rr": rr,
                    "trail_activate_pct": ta, "trail_pct": tp,
                    "breakeven_activate_pct": ba, "min_profit_hold_pct": mph,
                    "adx_thresh": adx_thresh, "rsi_buy": rsi_buy, "rsi_sell": 70,
                    "ema_fast": ema_fast, "ema_slow": ema_slow,
                }


def grid_donchian():
    for risk, sl, rr, ta, tp, ba, mph in product(
        COMMON_RISK, COMMON_SL, COMMON_RR, COMMON_TRAIL_ACT, COMMON_TRAIL, COMMON_BE_ACT, COMMON_MIN_PROFIT_HOLD
    ):
        for channel_period in [20, 40, 55]:
            yield {
                "strategy": "donchian",
                "risk_pct": risk, "stop_loss_pct": sl, "rr": rr,
                "trail_activate_pct": ta, "trail_pct": tp,
                "breakeven_activate_pct": ba, "min_profit_hold_pct": mph,
                "channel_period": channel_period,
            }


def grid_macd():
    for risk, sl, rr, ta, tp, ba, mph in product(
        COMMON_RISK, COMMON_SL, COMMON_RR, COMMON_TRAIL_ACT, COMMON_TRAIL, COMMON_BE_ACT, COMMON_MIN_PROFIT_HOLD
    ):
        yield {
            "strategy": "macd",
            "risk_pct": risk, "stop_loss_pct": sl, "rr": rr,
            "trail_activate_pct": ta, "trail_pct": tp,
            "breakeven_activate_pct": ba, "min_profit_hold_pct": mph,
        }


def grid_stochastic():
    for risk, sl, rr, ta, tp, ba, mph in product(
        COMMON_RISK, COMMON_SL, COMMON_RR, COMMON_TRAIL_ACT, COMMON_TRAIL, COMMON_BE_ACT, COMMON_MIN_PROFIT_HOLD
    ):
        yield {
            "strategy": "stochastic",
            "risk_pct": risk, "stop_loss_pct": sl, "rr": rr,
            "trail_activate_pct": ta, "trail_pct": tp,
            "breakeven_activate_pct": ba, "min_profit_hold_pct": mph,
        }


def grid_vol_breakout():
    for risk, sl, rr, ta, tp, ba, mph in product(
        COMMON_RISK, COMMON_SL, COMMON_RR, COMMON_TRAIL_ACT, COMMON_TRAIL, COMMON_BE_ACT, COMMON_MIN_PROFIT_HOLD
    ):
        for atr_mult_entry, atr_mult_trail, max_bars in product([1.0, 1.5, 2.0], [1.5, 2.0, 2.5], [48, 96]):
            yield {
                "strategy": "vol_breakout",
                "risk_pct": risk, "stop_loss_pct": sl, "rr": rr,
                "trail_activate_pct": ta, "trail_pct": tp,
                "breakeven_activate_pct": ba, "min_profit_hold_pct": mph,
                "atr_mult_entry": atr_mult_entry, "atr_mult_trail": atr_mult_trail,
                "max_bars": max_bars,
            }


def grid_williams():
    for risk, sl, rr, ta, tp, ba, mph in product(
        COMMON_RISK, COMMON_SL, COMMON_RR, COMMON_TRAIL_ACT, COMMON_TRAIL, COMMON_BE_ACT, COMMON_MIN_PROFIT_HOLD
    ):
        yield {
            "strategy": "williams",
            "risk_pct": risk, "stop_loss_pct": sl, "rr": rr,
            "trail_activate_pct": ta, "trail_pct": tp,
            "breakeven_activate_pct": ba, "min_profit_hold_pct": mph,
        }


GRID_FUNCS = {
    "rsi": grid_rsi,
    "ema_cross": grid_ema_cross,
    "bb": grid_bb,
    "supertrend": grid_supertrend,
    "regime_switch": grid_regime_switch,
    "donchian": grid_donchian,
    "macd": grid_macd,
    "stochastic": grid_stochastic,
    "vol_breakout": grid_vol_breakout,
    "williams": grid_williams,
}


# =========================================================================== #
# Indicator cache builder
# =========================================================================== #
def precompute_indicators(bars: dict[str, np.ndarray]) -> dict:
    """Pre-compute ALL indicators needed by ANY strategy. Return dict of arrays."""
    close = bars["close"]
    high = bars["high"]
    low = bars["low"]
    n = len(close)
    print(f"  Pre-computing indicators for {n} bars...")

    cache = {}
    # EMAs
    for p in [9, 12, 21, 26, 50, 100, 200]:
        cache[f"ema_{p}"] = ema(close, p)
    # RSI
    cache["rsi_14"] = wilder_rsi(close, 14)
    # ATR
    cache["atr_10"] = atr(high, low, close, 10)
    cache["atr_14"] = atr(high, low, close, 14)
    # ADX
    adx_val, plus_di, minus_di = adx(high, low, close, 14)
    cache["adx_14"] = adx_val
    cache["plus_di_14"] = plus_di
    cache["minus_di_14"] = minus_di
    # Bollinger Bands
    for std in [2.0, 2.5, 3.0]:
        u, m, lo = bollinger_bands(close, 20, std)
        cache[f"bb_upper_{std}"] = u
        cache[f"bb_mid_{std}"] = m
        cache[f"bb_lower_{std}"] = lo
    # Supertrend
    for atr_p, atr_m in [(10, 2.0), (10, 2.5), (10, 3.0), (10, 3.5),
                          (14, 2.0), (14, 2.5), (14, 3.0), (14, 3.5)]:
        st_val, st_dir = supertrend(high, low, close, atr_p, atr_m)
        cache[f"st_val_{atr_p}_{atr_m}"] = st_val
        cache[f"st_dir_{atr_p}_{atr_m}"] = st_dir
    # MACD
    cache["macd_line"] = cache["ema_12"] - cache["ema_26"]
    cache["macd_signal"] = ema(cache["macd_line"], 9)
    # Stochastic
    cache["stoch_k"], cache["stoch_d"] = stochastic(high, low, close, 14, 3)
    # Donchian
    for p in [20, 40, 55]:
        u, lo = donchian_channel(high, low, p)
        cache[f"dc_upper_{p}"] = u
        cache[f"dc_lower_{p}"] = lo
    # Williams %R
    cache["williams_r_14"] = williams_pct_r(high, low, close, 14)
    # Regime
    cache["regime"] = classify_regime(close, cache["ema_200"])

    print(f"  Cached {len(cache)} indicator arrays")
    return cache


# =========================================================================== #
# Signal generation dispatcher
# =========================================================================== #
def build_signals_for_combo(params: dict, cache: dict, bars: dict[str, np.ndarray]) -> Tuple[np.ndarray, np.ndarray, int, int]:
    """Returns (buy, sell, warmup, max_bars_in_trade)."""
    close = bars["close"]
    strategy = params["strategy"]

    if strategy == "rsi":
        rsi = cache["rsi_14"]
        ema_s = cache[f"ema_{params['ema_slow']}"]
        buy, sell = signals_rsi(close, rsi, ema_s, params["rsi_buy"], params["rsi_sell"], params["require_trend"])
        warmup = max(params["ema_slow"], 14, 200) + 1  # 200 for regime
        return buy, sell, warmup, 0

    elif strategy == "ema_cross":
        ema_f = cache[f"ema_{params['ema_fast']}"]
        ema_s = cache[f"ema_{params['ema_slow']}"]
        buy, sell = signals_ema_cross(ema_f, ema_s)
        warmup = max(params["ema_slow"], 200) + 1
        return buy, sell, warmup, 0

    elif strategy == "bb":
        bb_std = params["bb_std"]
        bb_u = cache[f"bb_upper_{bb_std}"]
        bb_l = cache[f"bb_lower_{bb_std}"]
        buy, sell = signals_bb(close, bb_u, bb_l)
        warmup = max(20, 200) + 1
        return buy, sell, warmup, 0

    elif strategy == "supertrend":
        atr_p = params["atr_period"]
        atr_m = params["atr_mult"]
        st_dir = cache[f"st_dir_{atr_p}_{atr_m}"]
        buy, sell = signals_supertrend(st_dir)
        warmup = max(atr_p, 200) + 1
        return buy, sell, warmup, 0

    elif strategy == "regime_switch":
        ema_f = cache[f"ema_{params['ema_fast']}"]
        ema_s = cache[f"ema_{params['ema_slow']}"]
        rsi = cache["rsi_14"]
        adx_val = cache["adx_14"]
        plus_di = cache["plus_di_14"]
        minus_di = cache["minus_di_14"]
        buy, sell = signals_regime_switch(
            close, rsi, ema_f, ema_s, adx_val, plus_di, minus_di,
            params["adx_thresh"], params["rsi_buy"], params["rsi_sell"]
        )
        warmup = max(params["ema_slow"], 28, 200) + 1  # 28 for ADX warmup
        return buy, sell, warmup, 0

    elif strategy == "donchian":
        cp = params["channel_period"]
        dc_u = cache[f"dc_upper_{cp}"]
        dc_l = cache[f"dc_lower_{cp}"]
        buy, sell = signals_donchian(close, dc_u, dc_l)
        warmup = max(cp, 200) + 1
        return buy, sell, warmup, 0

    elif strategy == "macd":
        macd_line = cache["macd_line"]
        macd_signal = cache["macd_signal"]
        buy, sell = signals_macd(macd_line, macd_signal)
        warmup = max(26, 200) + 1
        return buy, sell, warmup, 0

    elif strategy == "stochastic":
        pct_k = cache["stoch_k"]
        pct_d = cache["stoch_d"]
        buy, sell = signals_stochastic(pct_k, pct_d, 20, 80)
        warmup = max(14, 200) + 1
        return buy, sell, warmup, 0

    elif strategy == "vol_breakout":
        atr_val = cache["atr_14"]
        buy, sell = signals_vol_breakout(close, atr_val, params["atr_mult_entry"])
        warmup = max(14, 200) + 1
        return buy, sell, warmup, params["max_bars"]

    elif strategy == "williams":
        pct_r = cache["williams_r_14"]
        buy, sell = signals_williams(pct_r, -80, -20)
        warmup = max(14, 200) + 1
        return buy, sell, warmup, 0

    else:
        raise ValueError(f"Unknown strategy: {strategy}")


# =========================================================================== #
# Year-by-year analysis
# =========================================================================== #
def year_breakdown(bars, buy, sell, regime, params, cache, start_equity, fee_pct, warmup):
    """Run simulation per calendar year and return dict of year -> results."""
    ts = bars["ts"]
    years = sorted(set(int(t) for t in ts.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970))
    # Actually, compute years from timestamps
    years_dict = {}
    for y in years:
        # Find bar indices for this year
        start_ts = int(np.datetime64(f"{y}-01-01").astype("datetime64[s]").astype(int))
        end_ts = int(np.datetime64(f"{y+1}-01-01").astype("datetime64[s]").astype(int))
        mask = (ts >= start_ts) & (ts < end_ts)
        if mask.sum() < 100:
            continue
        # Create sub-bar view
        sub_bars = {k: v[mask] for k, v in bars.items()}
        sub_buy = buy[mask]
        sub_sell = sell[mask]
        sub_regime = regime[mask]
        # Run simulation on this year only with $110 start equity
        rets, eq, wins, mdd, rstats = simulate(
            sub_bars, sub_buy, sub_sell, sub_regime,
            start_equity=start_equity, risk_pct=params["risk_pct"],
            stop_loss_pct=params["stop_loss_pct"], rr=params["rr"],
            trail_activate_pct=params["trail_activate_pct"],
            trail_pct=params["trail_pct"],
            breakeven_activate_pct=params["breakeven_activate_pct"],
            min_profit_hold_pct=params["min_profit_hold_pct"],
            fee_pct=fee_pct, micro_account_threshold=200.0,
            confidence_floor=0.6, asset_multiplier=0.80,
            min_notional=5.0, warmup=min(warmup, len(sub_bars["close"]) // 2),
        )
        n_trades = len(rets)
        n_wins = sum(wins)
        wr = n_wins / n_trades if n_trades else 0
        final_eq = eq[-1]
        net_ret = (final_eq / start_equity - 1) * 100
        years_dict[y] = {"trades": n_trades, "wins": n_wins, "win_rate": wr, "net_return_pct": net_ret, "max_dd_pct": mdd}
    return years_dict


# =========================================================================== #
# Main runner
# =========================================================================== #
def run(args: argparse.Namespace) -> None:
    csv_path = Path(args.data)
    if not csv_path.exists():
        print(f"ERROR: data file not found: {csv_path}")
        print("Run scripts/research/fetch_btc_history.py first.")
        sys.exit(1)

    bars = load_csv(csv_path)
    n = len(bars["close"])
    days = (bars["ts"][-1] - bars["ts"][0]) / 86400
    print(f"Loaded {n} bars ({days:.1f} days)")

    cache = precompute_indicators(bars)
    regime = cache["regime"]

    # Determine which strategies to run
    if args.strategies == "all":
        strategies = ALL_STRATEGIES
    else:
        strategies = [s.strip() for s in args.strategies.split(",")]
        for s in strategies:
            if s not in ALL_STRATEGIES:
                print(f"ERROR: unknown strategy '{s}'. Choose from: {ALL_STRATEGIES}")
                sys.exit(1)

    # Count total combos
    total_combos = 0
    for s in strategies:
        count = sum(1 for _ in GRID_FUNCS[s]())
        print(f"  {s}: {count:,} combos")
        total_combos += count
    print(f"Total combos: {total_combos:,}")

    # Run sweep
    results: list[Result] = []
    t0 = time.time()
    last_print = t0
    combo_idx = 0

    for strategy_name in strategies:
        print(f"\n=== Strategy: {strategy_name} ===")
        grid_fn = GRID_FUNCS[strategy_name]
        strat_t0 = time.time()
        strat_count = 0

        for params in grid_fn():
            combo_idx += 1
            strat_count += 1
            buy, sell, warmup, max_bars = build_signals_for_combo(params, cache, bars)

            rets, eq_curve, wins, mdd, rstats = simulate(
                bars, buy, sell, regime,
                start_equity=args.start_equity,
                risk_pct=params["risk_pct"],
                stop_loss_pct=params["stop_loss_pct"],
                rr=params["rr"],
                trail_activate_pct=params["trail_activate_pct"],
                trail_pct=params["trail_pct"],
                breakeven_activate_pct=params["breakeven_activate_pct"],
                min_profit_hold_pct=params["min_profit_hold_pct"],
                fee_pct=args.fee_pct,
                micro_account_threshold=200.0,
                confidence_floor=0.6,
                asset_multiplier=0.80,
                min_notional=5.0,
                warmup=warmup,
                max_bars_in_trade=max_bars,
            )

            n_trades = len(rets)
            n_wins = sum(wins)
            wr = (n_wins / n_trades) if n_trades else 0.0
            final_eq = eq_curve[-1]
            net_ret = (final_eq / args.start_equity - 1.0) * 100.0
            if rets:
                wins_arr = np.array([r for r in rets if r > 0])
                losses_arr = np.array([r for r in rets if r <= 0])
                gw = wins_arr.sum() if wins_arr.size else 0.0
                gl = -losses_arr.sum() if losses_arr.size else 0.0
                pf = (gw / gl) if gl > 0 else (float("inf") if gw > 0 else 0.0)
                aw = wins_arr.mean() if wins_arr.size else 0.0
                al = losses_arr.mean() if losses_arr.size else 0.0
                mu = float(np.mean(rets))
                sd = float(np.std(rets)) or 1e-9
                sharpe_like = (mu / sd) * math.sqrt(max(n_trades, 1))
            else:
                pf = 0.0; aw = 0.0; al = 0.0; sharpe_like = 0.0

            # Build strategy_params JSON (exclude common params)
            common_keys = {"strategy", "risk_pct", "stop_loss_pct", "rr",
                          "trail_activate_pct", "trail_pct", "breakeven_activate_pct",
                          "min_profit_hold_pct"}
            sp = {k: v for k, v in params.items() if k not in common_keys}

            results.append(Result(
                strategy=strategy_name,
                risk_pct=params["risk_pct"], stop_loss_pct=params["stop_loss_pct"],
                rr=params["rr"], trail_activate_pct=params["trail_activate_pct"],
                trail_pct=params["trail_pct"], breakeven_activate_pct=params["breakeven_activate_pct"],
                min_profit_hold_pct=params["min_profit_hold_pct"],
                strategy_params=json.dumps(sp),
                trades=n_trades, wins=n_wins, win_rate=wr,
                final_equity=final_eq, net_return_pct=net_ret,
                max_drawdown_pct=mdd, profit_factor=pf if math.isfinite(pf) else 999.0,
                avg_win_pct=aw, avg_loss_pct=al, sharpe_like=sharpe_like,
                bull_trades=rstats["bull_trades"], bear_trades=rstats["bear_trades"],
                range_trades=rstats["range_trades"],
                bull_pnl_pct=rstats["bull_pnl_pct"], bear_pnl_pct=rstats["bear_pnl_pct"],
                range_pnl_pct=rstats["range_pnl_pct"],
                days=days,
            ))

            if time.time() - last_print > 5:
                done = combo_idx
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (total_combos - done) / rate
                print(f"  {done:,}/{total_combos:,} ({rate:.0f}/s) ETA {eta:.0f}s  [{strategy_name} #{strat_count}]")
                last_print = time.time()

        strat_elapsed = time.time() - strat_t0
        print(f"  {strategy_name}: {strat_count:,} combos in {strat_elapsed:.1f}s")

    elapsed = time.time() - t0
    print(f"\nDone. {len(results):,} combos in {elapsed:.1f}s ({len(results)/elapsed:.0f}/s)")

    # ---- Save raw JSON ----
    out_json = Path("docs/research/mega_sweep_results.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    def _scrub(v):
        if isinstance(v, np.generic):
            v = v.item()
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                return None
        return v
    payload = {
        "data_file": str(csv_path),
        "bars": n,
        "days": days,
        "start_equity": args.start_equity,
        "fee_pct": args.fee_pct,
        "n_combos": len(results),
        "results": [{k: _scrub(v) for k, v in asdict(r).items()} for r in results],
    }
    with out_json.open("w") as f:
        json.dump(payload, f)
    print(f" raw -> {out_json}")

    # ---- Generate report ----
    generate_report(results, days, args)


def generate_report(results: list[Result], days: float, args: argparse.Namespace) -> None:
    out_md = Path("docs/research/MEGA_SWEEP_RESULTS.md")
    min_trades = 8
    qualified = [r for r in results if r.trades >= min_trades]

    lines = []
    lines.append("# Mega Multi-Strategy Backtest Sweep — 5-Year Results")
    lines.append("")
    lines.append(f"- **Data**: `{args.data}` ({days:.1f} days, ~5 years of real BTC/USDT 1h candles)")
    lines.append(f"- **Start equity**: ${args.start_equity:.2f}")
    lines.append(f"- **Fee per side**: {args.fee_pct*100:.2f}%")
    lines.append(f"- **Total combos tested**: {len(results):,}")
    lines.append(f"- **Qualified (>={min_trades} trades)**: {len(qualified):,}")
    n_profit = sum(1 for r in qualified if r.net_return_pct > 0)
    pct_profit = (n_profit / len(qualified) * 100) if qualified else 0.0
    lines.append(f"- **Profitable (net > 0)**: {n_profit:,} ({pct_profit:.1f}%)")
    lines.append("")
    lines.append("## Strategies Tested")
    lines.append("")
    for s in ALL_STRATEGIES:
        strat_res = [r for r in results if r.strategy == s]
        strat_qual = [r for r in strat_res if r.trades >= min_trades]
        strat_profit = sum(1 for r in strat_qual if r.net_return_pct > 0)
        strat_pct = (strat_profit / len(strat_qual) * 100) if strat_qual else 0.0
        best = max(strat_qual, key=lambda r: r.net_return_pct) if strat_qual else None
        best_ret = f"{best.net_return_pct:+.1f}%" if best else "N/A"
        lines.append(f"- **{s}**: {len(strat_res):,} combos, {len(strat_qual):,} qualified, {strat_profit:,} profitable ({strat_pct:.1f}%), best={best_ret}")
    lines.append("")

    # ---- Per-strategy top configs ----
    lines.append("## Per-Strategy Top Configs (by net_return_pct - 0.5 * max_drawdown_pct)")
    lines.append("")
    for s in ALL_STRATEGIES:
        strat_qual = [r for r in qualified if r.strategy == s]
        strat_qual.sort(key=lambda r: r.net_return_pct - 0.5 * r.max_drawdown_pct, reverse=True)
        top_n = strat_qual[:args.top]
        if not top_n:
            lines.append(f"### {s} — No qualified configs")
            lines.append("")
            continue
        lines.append(f"### {s} — Top {len(top_n)}")
        lines.append("")
        lines.append("| # | Risk% | SL% | R:R | Trail | Trades | WR | Net% | MaxDD% | PF | Bull/Bear/Range trades |")
        lines.append("|---|------:|----:|----:|-------:|-------:|---:|-----:|-------:|---:|:-----------------------:|")
        for i, r in enumerate(top_n, 1):
            score = r.net_return_pct - 0.5 * r.max_drawdown_pct
            lines.append(
                f"| {i} | {r.risk_pct*100:.2f} | {r.stop_loss_pct:.1f} | {r.rr:.1f} "
                f"| {r.trail_activate_pct:.1f}/{r.trail_pct:.1f} "
                f"| {r.trades} | {r.win_rate*100:.0f}% "
                f"| {r.net_return_pct:+.1f} | {r.max_drawdown_pct:.1f} "
                f"| {r.profit_factor:.2f} "
                f"| {r.bull_trades}/{r.bear_trades}/{r.range_trades} |"
            )
        lines.append("")

    # ---- Regime analysis ----
    lines.append("## Regime Analysis")
    lines.append("")
    lines.append("Which strategies work best in each regime (bull/bear/range)?")
    lines.append("")

    # Per-regime: average PnL per trade for each strategy
    for regime_name, regime_key in [("BULL", "bull"), ("BEAR", "bear"), ("RANGE", "range")]:
        lines.append(f"### {regime_name} regime")
        lines.append("")
        strat_regime = []
        for s in ALL_STRATEGIES:
            strat_qual = [r for r in qualified if r.strategy == s]
            total_trades = sum(getattr(r, f"{regime_key}_trades") for r in strat_qual)
            total_pnl = sum(getattr(r, f"{regime_key}_pnl_pct") for r in strat_qual)
            avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
            strat_regime.append((s, total_trades, total_pnl, avg_pnl))
        strat_regime.sort(key=lambda x: x[3], reverse=True)
        lines.append("| Strategy | Regime Trades | Total PnL% | Avg PnL/trade% |")
        lines.append("|----------|-------------:|-----------:|---------------:|")
        for s, tt, tp, ap in strat_regime:
            lines.append(f"| {s} | {tt:,} | {tp:+.1f} | {ap:+.3f} |")
        lines.append("")

    # ---- Risk level analysis ----
    lines.append("## Risk Level Analysis (across all strategies)")
    lines.append("")
    lines.append("| Risk% | Combos | Profitable | Profit% | Avg Net% | Best Net% | Avg MaxDD% |")
    lines.append("|------:|-------:|-----------:|--------:|--------:|---------:|----------:|")
    for rp in sorted(set(r.risk_pct for r in qualified)):
        subset = [r for r in qualified if r.risk_pct == rp]
        n_prof = sum(1 for r in subset if r.net_return_pct > 0)
        avg_net = np.mean([r.net_return_pct for r in subset]) if subset else 0
        best_net = max((r.net_return_pct for r in subset), default=0)
        avg_dd = np.mean([r.max_drawdown_pct for r in subset]) if subset else 0
        pct = n_prof / len(subset) * 100 if subset else 0
        lines.append(f"| {rp*100:.2f} | {len(subset):,} | {n_prof:,} | {pct:.1f} | {avg_net:+.1f} | {best_net:+.1f} | {avg_dd:.1f} |")
    lines.append("")

    # ---- Best overall ----
    all_qual = sorted(qualified, key=lambda r: r.net_return_pct - 0.5 * r.max_drawdown_pct, reverse=True)
    if all_qual:
        b = all_qual[0]
        lines.append("## Best Overall Configuration")
        lines.append("")
        lines.append(f"- **Strategy**: {b.strategy}")
        lines.append(f"- **Strategy params**: {b.strategy_params}")
        lines.append(f"- **Risk**: {b.risk_pct*100:.2f}%")
        lines.append(f"- **SL**: {b.stop_loss_pct:.1f}%")
        lines.append(f"- **R:R**: {b.rr:.1f}")
        lines.append(f"- **Trail**: {b.trail_activate_pct:.1f}% / {b.trail_pct:.1f}%")
        lines.append(f"- **Trades**: {b.trades}")
        lines.append(f"- **Win rate**: {b.win_rate*100:.1f}%")
        lines.append(f"- **Net return**: {b.net_return_pct:+.2f}%")
        lines.append(f"- **Max drawdown**: {b.max_drawdown_pct:.2f}%")
        lines.append(f"- **Profit factor**: {b.profit_factor:.2f}")
        lines.append(f"- **Final equity**: ${b.final_equity:.2f}")
        lines.append(f"- **Regime trades**: Bull={b.bull_trades} Bear={b.bear_trades} Range={b.range_trades}")
        lines.append(f"- **Regime PnL**: Bull={b.bull_pnl_pct:+.1f}% Bear={b.bear_pnl_pct:+.1f}% Range={b.range_pnl_pct:+.1f}%")
        lines.append("")

    # ---- Top 20 overall ----
    lines.append("## Top 20 Overall (all strategies)")
    lines.append("")
    lines.append("| # | Strategy | Risk% | SL% | R:R | Trades | WR | Net% | MaxDD% | PF | Bull/Bear/Range |")
    lines.append("|---|----------|------:|----:|----:|-------:|---:|-----:|-------:|---:|:----------------:|")
    for i, r in enumerate(all_qual[:20], 1):
        lines.append(
            f"| {i} | {r.strategy} | {r.risk_pct*100:.2f} | {r.stop_loss_pct:.1f} | {r.rr:.1f} "
            f"| {r.trades} | {r.win_rate*100:.0f}% "
            f"| {r.net_return_pct:+.1f} | {r.max_drawdown_pct:.1f} "
            f"| {r.profit_factor:.2f} "
            f"| {r.bull_trades}/{r.bear_trades}/{r.range_trades} |"
        )
    lines.append("")

    # ---- Key findings ----
    lines.append("## Key Findings")
    lines.append("")
    # Which strategy has most profitable combos?
    strat_profit_counts = {}
    for s in ALL_STRATEGIES:
        strat_qual = [r for r in qualified if r.strategy == s]
        strat_profit_counts[s] = sum(1 for r in strat_qual if r.net_return_pct > 0)
    best_strat = max(strat_profit_counts, key=strat_profit_counts.get) if strat_profit_counts else "none"
    lines.append(f"- **Most profitable combos**: {best_strat} ({strat_profit_counts.get(best_strat, 0):,})")
    # Which risk level has most profitable combos?
    risk_profit = {}
    for rp in sorted(set(r.risk_pct for r in qualified)):
        subset = [r for r in qualified if r.risk_pct == rp]
        risk_profit[rp] = sum(1 for r in subset if r.net_return_pct > 0)
    if risk_profit:
        best_risk = max(risk_profit, key=risk_profit.get)
        lines.append(f"- **Best risk level**: {best_risk*100:.2f}% ({risk_profit[best_risk]:,} profitable combos)")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"_Generated by `scripts/research/run_mega_sweep.py`._")
    lines.append(f"_Strategies: {', '.join(ALL_STRATEGIES)}._")
    lines.append("_Spot-long-only, single position, 0.1% taker fee each side, compounding equity._")
    lines.append("_Regime: BULL (close > EMA200 + slope > 0), BEAR (close < EMA200 + slope < 0), RANGE (else)._")
    lines.append("_IMPORTANT: This uses REAL KuCoin 5-year OHLCV data._")
    lines.append("")

    out_md.write_text("\n".join(lines))
    print(f" report -> {out_md}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Mega multi-strategy backtest sweep")
    ap.add_argument("--data", default="data/btc_usdt_1h.csv", help="Path to 1h CSV data")
    ap.add_argument("--start-equity", type=float, default=110.0)
    ap.add_argument("--fee-pct", type=float, default=0.001)
    ap.add_argument("--top", type=int, default=5, help="Top N configs per strategy in report")
    ap.add_argument("--strategies", default="all", help="Comma-separated strategy list or 'all'")
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
