# Cross-Timeframe Mega Sweep Analysis — BTC/USDT 5-Year Real Data

**Date**: 2026-06-03
**Data**: KuCoin BTC/USDT OHLCV, 2021-06-04 → 2026-06-03
**Start equity**: $110
**Position**: Spot-long-only, single position, compounding

---

## Executive Summary

| Timeframe | Fee | Combos | Qualified | Profitable | Profit% | Best Strategy | Best Net% |
|-----------|-----|-------:|----------:|-----------:|--------:|---------------|----------:|
| 1h | 0.10% taker | 32,256 | 29,232 | 0 | 0.0% | N/A | -0.3% |
| 4h | 0.10% taker | 30,744 | 26,964 | 546 | 2.0% | ema_cross | +8.5% |
| 4h | 0.05% maker | 30,744 | 26,964 | 1,365 | 5.1% | ema_cross | +16.2% |
| 1d | 0.10% taker | 32,256 | 22,932 | 18,097 | 78.9% | vol_breakout | +69.9% |
| 1d | 0.05% maker | 32,256 | 22,932 | 19,015 | 82.9% | vol_breakout | +83.0% |

**Key finding**: Timeframe is the single most important variable. 1h has zero edge, 4h has modest edge, 1d has massive edge. Fee reduction (maker vs taker) roughly doubles the profitable config count on 4h but only marginally improves on 1d (where edge is already large).

---

## 1-Hour Timeframe: ZERO EDGE

- **0 profitable configs** across all 10 strategies, 32,256 combinations
- Even BULL regime trades lose money after 0.2% round-trip fees
- Best: RSI with EMA100 trend filter, -0.34% over 5 years (8 trades only)
- **Verdict**: 1h timeframe is untradable at $110 with taker fees. Too noisy, fees eat all edge.

---

## 4-Hour Timeframe: MODEST EDGE

### Taker Fee (0.1% per side = 0.2% round-trip)

| Strategy | Qualified | Profitable | Best Net% |
|----------|----------:|-----------:|----------:|
| ema_cross | 2,268 | 318 | +8.47% |
| vol_breakout | 4,536 | 228 | +1.72% |
| regime_switch | 9,072 | 0 | -0.54% |
| rsi | 8,316 | 0 | -0.70% |
| supertrend | 2,016 | 0 | -1.08% |
| bb | 756 | 0 | -3.96% |

### Maker Fee (0.05% per side = 0.1% round-trip)

| Strategy | Qualified | Profitable | Best Net% |
|----------|----------:|-----------:|----------:|
| ema_cross | 2,268 | 675 | +16.17% |
| vol_breakout | 4,536 | 606 | +8.51% |
| regime_switch | 9,072 | 57 | +1.81% |
| supertrend | 2,016 | 27 | +1.24% |
| rsi | 8,316 | 0 | -0.42% |
| bb | 756 | 0 | -3.67% |

### Best 4h Config: EMA21/200 Crossover

- **EMA pair**: EMA21/200 (79% of all profitable EMA Cross configs)
- **Stop loss**: 5.0% (wider is better on 4h)
- **Risk per trade**: 10% (more aggressive works because WR is high)
- **Trades**: 41 in 5 years (~8/year)
- **Win rate**: 66%
- **Net return**: +8.47% (taker) / +16.17% (maker)
- **Max drawdown**: 6.1%
- **Profit factor**: 1.60 (taker) / 2.10 (maker)
- **Regime profile**: Bull trades LOSE (-10.3%), Range trades WIN (+19.5%)
  - This is a RANGE strategy, not a trend strategy — EMA21/200 crossover on 4h captures mean-reversion after extended ranges
  - Zero bear regime trades — the EMA200 filter prevents entries in downtrends

---

## Daily Timeframe: MASSIVE EDGE

### Taker Fee (0.1% per side = 0.2% round-trip)

| Strategy | Qualified | Profitable | Profit% | Best Net% |
|----------|----------:|-----------:|--------:|----------:|
| vol_breakout | 4,536 | 4,536 | 100.0% | +69.88% |
| williams | 252 | 147 | 58.3% | +35.96% |
| rsi | 6,804 | 5,373 | 79.0% | +27.52% |
| supertrend | 2,016 | 1,974 | 97.9% | +29.62% |
| bb | 756 | 441 | 58.3% | +30.95% |
| regime_switch | 6,048 | 3,742 | 61.9% | +12.90% |
| ema_cross | 2,016 | 1,647 | 81.7% | +8.80% |
| macd | 252 | 231 | 91.7% | +21.70% |
| stochastic | 252 | 6 | 2.4% | +0.03% |
| donchian | 0 | 0 | N/A | N/A |

### Maker Fee (0.05% per side = 0.1% round-trip)

| Strategy | Qualified | Profitable | Profit% | Best Net% |
|----------|----------:|-----------:|--------:|----------:|
| vol_breakout | 4,536 | 4,536 | 100.0% | +83.00% |
| williams | 252 | 168 | 66.7% | +46.10% |
| rsi | 6,804 | 5,697 | 83.7% | +31.42% |
| supertrend | 2,016 | 1,974 | 97.9% | +31.70% |
| bb | 756 | 567 | 75.0% | +34.44% |
| macd | 252 | 231 | 91.7% | +27.02% |
| regime_switch | 6,048 | 4,066 | 67.2% | +15.27% |
| ema_cross | 2,016 | 1,722 | 85.4% | +9.52% |
| stochastic | 252 | 54 | 21.4% | +2.58% |
| donchian | 0 | 0 | N/A | N/A |

### Best 1d Config: Volatility Breakout

- **ATR entry multiplier**: 1.0 (close > prev_close + 1.0 * ATR14)
- **Risk per trade**: 2.0%
- **Stop loss**: 1.5%
- **Trades**: 97 in 5 years (~19/year)
- **Win rate**: 59%
- **Net return**: +69.88% (taker) / +83.00% (maker)
- **Max drawdown**: 11.0% (taker) / 7.5% (maker)
- **Profit factor**: 2.02 (taker) / 2.23 (maker)
- **100% of vol_breakout configs are profitable on 1d** — this strategy is robust

### Other Strong 1d Strategies

- **Williams %R**: +46.10% best (maker), 96 trades, 46% WR but very high R:R
- **RSI**: +31.42% best (maker), 36 trades, 53% WR — the classic works on daily
- **Supertrend**: +31.70% best (maker), 22 trades, 64% WR — low trade count but high quality
- **BB Bounce**: +34.44% best (maker), 40 trades, 48% WR — mean reversion works on daily

---

## Why Daily Timeframe Works

1. **Less noise**: Daily candles filter out intraday volatility, signals are more meaningful
2. **Wider moves**: Each daily bar captures the full day's range — trades have more room to develop
3. **Lower fee impact**: Same 0.2% fee but on much larger per-trade moves (2-5% daily moves vs 0.5-1% hourly)
4. **Fewer false signals**: Crossover/breakout signals on daily are more reliable
5. **Better R:R**: Wider stops mean fewer stop-outs, and winners run further

---

## Recommended Configurations for $110 Account

### Conservative (Lowest Drawdown)
- **Timeframe**: 1d
- **Strategy**: Supertrend
- **Risk**: 0.5-1.0%
- **Expected**: ~20% net over 5 years, ~3-5% max DD, ~22 trades

### Moderate (Best Risk-Adjusted)
- **Timeframe**: 1d
- **Strategy**: RSI Oversold (rsi_buy=35-40, ema_slow=100, require_trend=True)
- **Risk**: 0.75-2.0%
- **Expected**: ~25-30% net over 5 years, ~8-10% max DD, ~36 trades

### Aggressive (Maximum Return)
- **Timeframe**: 1d
- **Strategy**: Volatility Breakout (atr_mult_entry=1.0)
- **Risk**: 2.0%
- **Expected**: ~70-83% net over 5 years, ~7-11% max DD, ~97 trades

### 4h Alternative (More Frequent Trading)
- **Timeframe**: 4h
- **Strategy**: EMA21/200 Crossover
- **Risk**: 10%
- **Fee**: Maker orders (limit orders only)
- **Expected**: ~16% net over 5 years, ~6% max DD, ~41 trades

---

## Action Items

1. **Switch bot from 1h to 1d candle interval** — the data is overwhelming
2. **Implement Volatility Breakout strategy** in the bot (or Supertrend as conservative option)
3. **Use limit orders** (maker fee) instead of market orders wherever possible
4. **Do NOT go live yet** — implement 1d strategies in paper mode first
5. **Run 30+ paper trades** on 1d Vol Breakout / Supertrend before live cutover
6. **Keep R:R ≥ 2.0** — the daily strategies naturally produce high R:R trades

---

_Generated from mega_sweep results across 1h/4h/1d timeframes with taker/maker fee variants._
_32,256 combos per timeframe × 3 timeframes × 2 fee levels = ~195,000 total combinations tested._
_Data: Real KuCoin BTC/USDT OHLCV, 2021-06-04 → 2026-06-03._