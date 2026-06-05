# Strategy Catalog — BTC/USDT Micro-Account Backtesting

**Purpose:** Comprehensive list of strategies to test on 5 years of BTC/USDT historical data (2021-2026) with $110 starting equity.

---

## Category 1: Mean Reversion (Ranging Markets)

### 1.1 RSI Oversold Bounce (CURRENT STRATEGY)
- **Entry:** RSI crosses above rsi_buy (25/30/35/40) from below
- **Exit:** RSI crosses below rsi_sell (65/70/75) from above, OR stop loss, OR R:R take-profit
- **Params:** rsi_period=14, rsi_buy, rsi_sell, stop_loss_pct, rr, trail_pct, breakeven_pct
- **Regime:** Range/sideways. FAILS in sustained downtrend.
- **Expected WR:** 40-60% depending on regime
- **R:R:** 1.5-3.0
- **Frequency:** 1-3 trades/week on 1h
- **Failure:** Sustained trends (bears eat oversold bounces)

### 1.2 Bollinger Band Bounce
- **Entry:** Close crosses below lower BB, then closes back inside (above lower BB)
- **Exit:** Close touches upper BB, OR stop loss below recent low, OR R:R TP
- **Params:** bb_period=20, bb_std=2.0/2.5/3.0, stop_loss_pct, rr
- **Regime:** Range. BB squeeze = upcoming breakout (don't enter during squeeze)
- **Expected WR:** 50-65%
- **R:R:** 1.5-2.5
- **Frequency:** 1-2 trades/week on 1h
- **Failure:** Strong trends push price along BB edge

### 1.3 Stochastic Oscillator
- **Entry:** %K crosses above %D when both below oversold (20)
- **Exit:** %K crosses below %D when both above overbought (80), OR SL, OR TP
- **Params:** k_period=14, d_period=3, smooth=3, oversold=20, overbought=80
- **Regime:** Range
- **Expected WR:** 45-60%
- **R:R:** 1.5-2.5
- **Frequency:** 2-4 trades/week on 1h
- **Failure:** Same as RSI — sustained trends

### 1.4 VWAP Reversion (intraday only)
- **Entry:** Price deviates X% below VWAP, then crosses back above
- **Exit:** Price reaches VWAP + Y% (take profit), OR SL below deviation low
- **Params:** deviation_pct=1.0/1.5/2.0, tp_pct, sl_pct
- **Regime:** Range/intraday mean-reversion
- **Expected WR:** 55-65%
- **R:R:** 1.0-2.0
- **Frequency:** 1-2 trades/day on 1h
- **Failure:** Trend days where price stays away from VWAP

---

## Category 2: Trend Following (Trending Markets)

### 2.1 Dual EMA Crossover
- **Entry:** Fast EMA crosses above Slow EMA (golden cross)
- **Exit:** Fast EMA crosses below Slow EMA (death cross), OR trailing stop
- **Params:** ema_fast=9/12/21, ema_slow=21/50/100/200, trail_pct
- **Regime:** Bull trend. FAILS in ranging markets (whipsaws).
- **Expected WR:** 30-45% (high R:R compensates)
- **R:R:** 2.0-5.0
- **Frequency:** 1-2 trades/month on 1h
- **Failure:** Choppy/ranging markets cause repeated false crossovers

### 2.2 MACD Signal Crossover
- **Entry:** MACD line crosses above signal line AND MACD histogram > 0
- **Exit:** MACD crosses below signal, OR trailing stop
- **Params:** macd_fast=12, macd_slow=26, macd_signal=9, trail_pct
- **Regime:** Trend
- **Expected WR:** 35-50%
- **R:R:** 2.0-4.0
- **Frequency:** 1-3 trades/week on 4h
- **Failure:** Ranging markets cause whipsaws

### 2.3 Supertrend
- **Entry:** Supertrend flips from red (bearish) to green (bullish)
- **Exit:** Supertrend flips back to red, OR trailing stop below supertrend line
- **Params:** atr_period=10/14/20, atr_multiplier=2.0/2.5/3.0/3.5
- **Regime:** Trend
- **Expected WR:** 35-50%
- **R:R:** 2.0-5.0
- **Frequency:** 1-2 trades/week on 4h
- **Failure:** Choppy markets cause rapid flips

### 2.4 Donchian Channel Breakout
- **Entry:** Close breaks above N-period high (channel upper)
- **Exit:** Close breaks below N-period low (channel lower), OR trailing stop
- **Params:** channel_period=20/40/55 (classic turtle), trail_pct
- **Regime:** Trend/breakout
- **Expected WR:** 30-40% (very high R:R)
- **R:R:** 3.0-8.0
- **Frequency:** 1-4 trades/month on 1d
- **Failure:** False breakouts in ranging markets

### 2.5 Parabolic SAR
- **Entry:** SAR dots flip from above price to below price (buy signal)
- **Exit:** SAR dots flip back above price, OR SL
- **Params:** af_step=0.02, af_max=0.2
- **Regime:** Strong trend
- **Expected WR:** 35-45%
- **R:R:** 1.5-4.0
- **Frequency:** 3-5 trades/week on 1h
- **Failure:** Ranging markets — SAR whipsaws constantly

---

## Category 3: Momentum

### 3.1 ADX + DI
- **Entry:** +DI crosses above -DI AND ADX > threshold (20/25/30)
- **Exit:** +DI crosses below -DI, OR ADX drops below threshold, OR trailing
- **Params:** adx_period=14, adx_threshold=20/25/30, trail_pct
- **Regime:** Trending (ADX confirms trend strength)
- **Expected WR:** 40-55%
- **R:R:** 2.0-4.0
- **Frequency:** 1-3 trades/week on 4h
- **Failure:** Low ADX periods generate no signals

### 3.2 Rate of Change (ROC) Momentum
- **Entry:** ROC crosses above zero from below AND ROC > entry_threshold
- **Exit:** ROC crosses below zero, OR SL, OR trailing
- **Params:** roc_period=12/21, entry_threshold=0/2/5, trail_pct
- **Regime:** Momentum/trend
- **Expected WR:** 40-50%
- **R:R:** 2.0-3.5
- **Frequency:** 1-2 trades/week on 4h

### 3.3 RSI Divergence (Bullish)
- **Entry:** Price makes lower low BUT RSI makes higher low (bullish divergence)
- **Exit:** RSI crosses above overbought, OR SL below divergence low, OR TP
- **Params:** rsi_period=14, lookback=10/20/30 bars for divergence detection
- **Regime:** Reversal (end of downtrend)
- **Expected WR:** 45-55%
- **R:R:** 2.0-4.0
- **Frequency:** 1-2 trades/month (rare signal)
- **Failure:** Divergence can extend (multiple divergences before reversal)

---

## Category 4: Hybrid/Adaptive

### 4.1 Regime Switch (ADX + RSI)
- **Entry:** If ADX > 25: use EMA crossover entry (trend mode). If ADX < 25: use RSI oversold entry (range mode)
- **Exit:** Strategy-specific exits + universal trailing stop
- **Params:** adx_threshold=25, ema_fast, ema_slow, rsi_buy, rsi_sell, trail_pct
- **Regime:** ADAPTIVE — switches between trend and range
- **Expected WR:** 45-60%
- **R:R:** 2.0-3.5
- **Frequency:** Variable
- **Key advantage:** Avoids mean-reversion entries during trends, avoids trend entries during ranges

### 4.2 Volatility Breakout (ATR Expansion)
- **Entry:** Price moves more than X * ATR from previous close (expansion detected)
- **Exit:** Trailing stop at Y * ATR, OR time-based exit (close after N bars)
- **Params:** atr_period=14, atr_multiplier_entry=1.0/1.5/2.0, atr_multiplier_trail=1.5/2.0/2.5, max_bars=48/96
- **Regime:** Volatile/breakout
- **Expected WR:** 35-50%
- **R:R:** 2.0-5.0
- **Frequency:** 2-5 trades/week on 1h
- **Failure:** Low volatility periods — no signals

### 4.3 Ichimoku Cloud
- **Entry:** Price crosses above cloud (senkou span A > B) AND tenkan > kijun
- **Exit:** Price crosses below cloud OR tenkan crosses below kijun
- **Params:** tenkan=9, kijun=26, senkou=52
- **Regime:** Trend (with cloud as dynamic S/R)
- **Expected WR:** 40-55%
- **R:R:** 2.0-4.0
- **Frequency:** 1-2 trades/month on 1d
- **Failure:** Inside-cloud price action is ambiguous

### 4.4 Multi-Timeframe Confluence
- **Entry:** 1h RSI oversold AND 4h trend is bullish (close > 4h EMA50) AND 1d not in downtrend
- **Exit:** 1h RSI overbought OR SL OR TP
- **Params:** rsi_buy, rsi_sell, ema_slow_4h=50, trend_filter_1d
- **Regime:** Bull pullbacks (buy the dip in uptrend)
- **Expected WR:** 50-65%
- **R:R:** 2.0-3.0
- **Frequency:** 1-3 trades/month
- **Key advantage:** Higher timeframe filter eliminates counter-trend entries

### 4.5 Williams %R
- **Entry:** %R crosses above -80 from below (oversold bounce)
- **Exit:** %R crosses below -20 from above, OR SL, OR TP
- **Params:** period=14, oversold=-80, overbought=-20
- **Regime:** Range
- **Expected WR:** 45-55%
- **R:R:** 1.5-2.5
- **Frequency:** 2-4 trades/week on 1h

---

## Category 5: Position Sizing Variants (Apply to ANY Strategy)

### 5.1 Fixed Fractional (Current)
- Risk X% of equity per trade
- Position = (equity * risk_pct) / (entry_price * stop_loss_pct)
- **Range:** risk_pct = 0.5% to 10%

### 5.2 Kelly Criterion
- risk_pct = win_rate - ((1 - win_rate) / avg_R_R)
- Half-Kelly for safety: risk_pct / 2
- Adapts to measured WR and R:R

### 5.3 Anti-Martingale (Increase After Win)
- After win: increase risk by X% (e.g., 50% more)
- After loss: reset to base risk
- **Range:** base_risk = 1-3%, increase = 25-100%

### 5.4 Martingale (Dangerous but test it)
- After loss: double position size
- After win: reset to base
- **WARNING:** Rapid account destruction possible. Test with tight SL only.

### 5.5 All-In / Max Aggression
- 90%+ of equity per trade
- Test to see absolute ceiling of what's possible
- **WARNING:** Single loss = account wipe

### 5.6 Position Count Variants
- 1 position (current)
- 2 positions (split risk)
- 3 positions (split risk further)
- 5 positions (diversified at micro scale)
- 10 positions (extreme diversification)

---

## Category 6: Exit Management Variants (Apply to ANY Strategy)

### 6.1 Fixed Stop + Fixed TP (Simplest)
- SL at X%, TP at SL * R:R
- No trailing, no breakeven

### 6.2 Trailing Stop Only
- Trail at Y% below peak after activation
- No fixed TP

### 6.3 Breakeven + Trailing (Current)
- Move SL to breakeven after Z% gain
- Then trail at Y% below peak

### 6.4 Time-Based Exit
- Close position after N bars regardless of P&L
- Test: N = 12/24/48/96/168 hours

### 6.5 Chandelier Exit (ATR-based)
- SL = peak - N * ATR(14)
- Adapts to volatility

---

## Implementation Priority

**Phase 1 — Core strategies (implement first):**
1. RSI Oversold Bounce (already done)
2. Dual EMA Crossover
3. Bollinger Band Bounce
4. Supertrend
5. Regime Switch (ADX + RSI/EMA)

**Phase 2 — Additional strategies:**
6. Donchian Channel Breakout
7. MACD Signal Crossover
8. Stochastic Oscillator
9. Volatility Breakout (ATR)
10. Multi-Timeframe Confluence

**Phase 3 — Advanced:**
11. Ichimoku Cloud
12. ADX + DI
13. RSI Divergence
14. Parabolic SAR
15. Williams %R
16. ROC Momentum

**Phase 4 — Sizing variants on best strategies:**
17. Kelly Criterion sizing
18. Anti-Martingale sizing
19. Multi-position variants
20. All-in / max aggression tests