# Mega Multi-Strategy Backtest Sweep — 5-Year Results

- **Data**: `data/btc_usdt_4h.csv` (1824.8 days, ~5 years of real BTC/USDT 1h candles)
- **Start equity**: $110.00
- **Fee per side**: 0.10%
- **Total combos tested**: 30,744
- **Qualified (>=8 trades)**: 26,964
- **Profitable (net > 0)**: 546 (2.0%)

## Strategies Tested

- **rsi**: 12,096 combos, 8,316 qualified, 0 profitable (0.0%), best=-0.7%
- **ema_cross**: 2,268 combos, 2,268 qualified, 318 profitable (14.0%), best=+8.5%
- **bb**: 756 combos, 756 qualified, 0 profitable (0.0%), best=-4.0%
- **supertrend**: 2,016 combos, 2,016 qualified, 0 profitable (0.0%), best=-1.1%
- **regime_switch**: 9,072 combos, 9,072 qualified, 0 profitable (0.0%), best=-0.5%
- **donchian**: 0 combos, 0 qualified, 0 profitable (0.0%), best=N/A
- **macd**: 0 combos, 0 qualified, 0 profitable (0.0%), best=N/A
- **stochastic**: 0 combos, 0 qualified, 0 profitable (0.0%), best=N/A
- **vol_breakout**: 4,536 combos, 4,536 qualified, 228 profitable (5.0%), best=+1.7%
- **williams**: 0 combos, 0 qualified, 0 profitable (0.0%), best=N/A

## Per-Strategy Top Configs (by net_return_pct - 0.5 * max_drawdown_pct)

### rsi — Top 5

| # | Risk% | SL% | R:R | Trail | Trades | WR | Net% | MaxDD% | PF | Bull/Bear/Range trades |
|---|------:|----:|----:|-------:|-------:|---:|-----:|-------:|---:|:-----------------------:|
| 1 | 0.50 | 5.0 | 1.5 | 1.5/1.5 | 18 | 61% | -0.7 | 1.1 | 0.44 | 13/4/1 |
| 2 | 0.50 | 5.0 | 1.5 | 1.5/1.5 | 18 | 61% | -0.7 | 1.1 | 0.44 | 13/4/1 |
| 3 | 0.50 | 5.0 | 1.5 | 1.5/1.5 | 18 | 61% | -0.7 | 1.1 | 0.44 | 13/4/1 |
| 4 | 0.50 | 5.0 | 1.5 | 2.0/1.5 | 18 | 61% | -0.7 | 1.1 | 0.44 | 13/4/1 |
| 5 | 0.50 | 5.0 | 1.5 | 2.0/1.5 | 18 | 61% | -0.7 | 1.1 | 0.44 | 13/4/1 |

### ema_cross — Top 5

| # | Risk% | SL% | R:R | Trail | Trades | WR | Net% | MaxDD% | PF | Bull/Bear/Range trades |
|---|------:|----:|----:|-------:|-------:|---:|-----:|-------:|---:|:-----------------------:|
| 1 | 10.00 | 5.0 | 1.5 | 1.5/1.5 | 41 | 66% | +8.5 | 6.1 | 1.60 | 16/0/25 |
| 2 | 10.00 | 5.0 | 2.0 | 1.5/1.5 | 41 | 66% | +8.5 | 6.1 | 1.60 | 16/0/25 |
| 3 | 10.00 | 5.0 | 3.0 | 1.5/1.5 | 41 | 66% | +8.5 | 6.1 | 1.60 | 16/0/25 |
| 4 | 50.00 | 5.0 | 1.5 | 1.5/1.5 | 41 | 66% | +8.5 | 6.1 | 1.60 | 16/0/25 |
| 5 | 50.00 | 5.0 | 2.0 | 1.5/1.5 | 41 | 66% | +8.5 | 6.1 | 1.60 | 16/0/25 |

### bb — Top 5

| # | Risk% | SL% | R:R | Trail | Trades | WR | Net% | MaxDD% | PF | Bull/Bear/Range trades |
|---|------:|----:|----:|-------:|-------:|---:|-----:|-------:|---:|:-----------------------:|
| 1 | 0.50 | 5.0 | 1.5 | 2.0/1.5 | 69 | 49% | -4.0 | 4.1 | 0.36 | 15/41/13 |
| 2 | 0.50 | 5.0 | 2.0 | 2.0/1.5 | 69 | 49% | -4.0 | 4.1 | 0.36 | 15/41/13 |
| 3 | 0.50 | 5.0 | 3.0 | 2.0/1.5 | 69 | 49% | -4.0 | 4.1 | 0.36 | 15/41/13 |
| 4 | 0.50 | 5.0 | 1.5 | 1.5/1.5 | 69 | 52% | -4.2 | 4.3 | 0.33 | 15/41/13 |
| 5 | 0.50 | 5.0 | 2.0 | 1.5/1.5 | 69 | 52% | -4.2 | 4.3 | 0.33 | 15/41/13 |

### supertrend — Top 5

| # | Risk% | SL% | R:R | Trail | Trades | WR | Net% | MaxDD% | PF | Bull/Bear/Range trades |
|---|------:|----:|----:|-------:|-------:|---:|-----:|-------:|---:|:-----------------------:|
| 1 | 0.50 | 5.0 | 1.5 | 1.5/1.5 | 104 | 72% | -1.1 | 1.7 | 0.80 | 33/46/25 |
| 2 | 0.50 | 5.0 | 2.0 | 1.5/1.5 | 104 | 72% | -1.1 | 1.7 | 0.80 | 33/46/25 |
| 3 | 0.50 | 5.0 | 3.0 | 1.5/1.5 | 104 | 72% | -1.1 | 1.7 | 0.80 | 33/46/25 |
| 4 | 0.50 | 5.0 | 1.5 | 2.0/1.5 | 104 | 70% | -1.1 | 1.8 | 0.79 | 33/46/25 |
| 5 | 0.50 | 5.0 | 2.0 | 2.0/1.5 | 104 | 70% | -1.1 | 1.8 | 0.79 | 33/46/25 |

### regime_switch — Top 5

| # | Risk% | SL% | R:R | Trail | Trades | WR | Net% | MaxDD% | PF | Bull/Bear/Range trades |
|---|------:|----:|----:|-------:|-------:|---:|-----:|-------:|---:|:-----------------------:|
| 1 | 0.50 | 5.0 | 1.5 | 2.0/1.5 | 74 | 54% | -0.7 | 1.7 | 0.75 | 21/34/19 |
| 2 | 0.50 | 5.0 | 2.0 | 2.0/1.5 | 74 | 54% | -0.7 | 1.7 | 0.75 | 21/34/19 |
| 3 | 0.50 | 5.0 | 3.0 | 2.0/1.5 | 74 | 54% | -0.7 | 1.7 | 0.75 | 21/34/19 |
| 4 | 0.50 | 3.0 | 1.5 | 1.5/1.5 | 58 | 52% | -0.5 | 2.2 | 0.85 | 13/25/20 |
| 5 | 0.50 | 3.0 | 2.0 | 1.5/1.5 | 58 | 52% | -0.5 | 2.2 | 0.85 | 13/25/20 |

### donchian — No qualified configs

### macd — No qualified configs

### stochastic — No qualified configs

### vol_breakout — Top 5

| # | Risk% | SL% | R:R | Trail | Trades | WR | Net% | MaxDD% | PF | Bull/Bear/Range trades |
|---|------:|----:|----:|-------:|-------:|---:|-----:|-------:|---:|:-----------------------:|
| 1 | 0.50 | 1.5 | 2.0 | 1.5/1.5 | 92 | 59% | +0.7 | 4.8 | 1.06 | 49/22/21 |
| 2 | 0.50 | 1.5 | 2.0 | 1.5/1.5 | 92 | 59% | +0.7 | 4.8 | 1.06 | 49/22/21 |
| 3 | 0.50 | 1.5 | 2.0 | 1.5/1.5 | 92 | 59% | +0.7 | 4.8 | 1.06 | 49/22/21 |
| 4 | 0.50 | 1.5 | 2.0 | 1.5/1.5 | 92 | 59% | +0.7 | 4.8 | 1.06 | 49/22/21 |
| 5 | 0.50 | 1.5 | 2.0 | 1.5/1.5 | 92 | 59% | +0.7 | 4.8 | 1.06 | 49/22/21 |

### williams — No qualified configs

## Regime Analysis

Which strategies work best in each regime (bull/bear/range)?

### BULL regime

| Strategy | Regime Trades | Total PnL% | Avg PnL/trade% |
|----------|-------------:|-----------:|---------------:|
| donchian | 0 | +0.0 | +0.000 |
| macd | 0 | +0.0 | +0.000 |
| stochastic | 0 | +0.0 | +0.000 |
| williams | 0 | +0.0 | +0.000 |
| vol_breakout | 674,415 | -144926.8 | -0.215 |
| regime_switch | 265,356 | -64560.0 | -0.243 |
| ema_cross | 49,896 | -15502.1 | -0.311 |
| rsi | 295,029 | -121848.2 | -0.413 |
| supertrend | 109,368 | -56572.6 | -0.517 |
| bb | 39,298 | -24459.5 | -0.622 |

### BEAR regime

| Strategy | Regime Trades | Total PnL% | Avg PnL/trade% |
|----------|-------------:|-----------:|---------------:|
| donchian | 0 | +0.0 | +0.000 |
| macd | 0 | +0.0 | +0.000 |
| stochastic | 0 | +0.0 | +0.000 |
| williams | 0 | +0.0 | +0.000 |
| vol_breakout | 405,300 | -72429.5 | -0.179 |
| supertrend | 150,444 | -43214.3 | -0.287 |
| rsi | 853,146 | -298186.2 | -0.350 |
| regime_switch | 490,497 | -171957.6 | -0.351 |
| ema_cross | 66,780 | -25380.3 | -0.380 |
| bb | 75,285 | -29100.3 | -0.387 |

### RANGE regime

| Strategy | Regime Trades | Total PnL% | Avg PnL/trade% |
|----------|-------------:|-----------:|---------------:|
| ema_cross | 69,300 | +436.5 | +0.006 |
| donchian | 0 | +0.0 | +0.000 |
| macd | 0 | +0.0 | +0.000 |
| stochastic | 0 | +0.0 | +0.000 |
| williams | 0 | +0.0 | +0.000 |
| vol_breakout | 182,742 | -6828.7 | -0.037 |
| supertrend | 43,596 | -5995.0 | -0.138 |
| regime_switch | 167,076 | -35287.3 | -0.211 |
| bb | 19,782 | -12365.3 | -0.625 |
| rsi | 109,242 | -92930.5 | -0.851 |

## Risk Level Analysis (across all strategies)

| Risk% | Combos | Profitable | Profit% | Avg Net% | Best Net% | Avg MaxDD% |
|------:|-------:|-----------:|--------:|--------:|---------:|----------:|
| 0.50 | 3,852 | 84 | 2.2 | -6.9 | +1.1 | 7.7 |
| 0.75 | 3,852 | 83 | 2.2 | -10.1 | +1.6 | 11.2 |
| 1.00 | 3,852 | 83 | 2.2 | -13.0 | +2.1 | 14.5 |
| 2.00 | 3,852 | 77 | 2.0 | -22.6 | +4.0 | 25.1 |
| 5.00 | 3,852 | 73 | 1.9 | -30.6 | +7.2 | 34.0 |
| 10.00 | 3,852 | 73 | 1.9 | -31.6 | +8.5 | 35.1 |
| 50.00 | 3,852 | 73 | 1.9 | -31.6 | +8.5 | 35.1 |

## Best Overall Configuration

- **Strategy**: ema_cross
- **Strategy params**: {"ema_fast": 21, "ema_slow": 200}
- **Risk**: 10.00%
- **SL**: 5.0%
- **R:R**: 1.5
- **Trail**: 1.5% / 1.5%
- **Trades**: 41
- **Win rate**: 65.9%
- **Net return**: +8.47%
- **Max drawdown**: 6.12%
- **Profit factor**: 1.60
- **Final equity**: $119.32
- **Regime trades**: Bull=16 Bear=0 Range=25
- **Regime PnL**: Bull=-10.3% Bear=+0.0% Range=+19.5%

## Top 20 Overall (all strategies)

| # | Strategy | Risk% | SL% | R:R | Trades | WR | Net% | MaxDD% | PF | Bull/Bear/Range |
|---|----------|------:|----:|----:|-------:|---:|-----:|-------:|---:|:----------------:|
| 1 | ema_cross | 10.00 | 5.0 | 1.5 | 41 | 66% | +8.5 | 6.1 | 1.60 | 16/0/25 |
| 2 | ema_cross | 10.00 | 5.0 | 2.0 | 41 | 66% | +8.5 | 6.1 | 1.60 | 16/0/25 |
| 3 | ema_cross | 10.00 | 5.0 | 3.0 | 41 | 66% | +8.5 | 6.1 | 1.60 | 16/0/25 |
| 4 | ema_cross | 50.00 | 5.0 | 1.5 | 41 | 66% | +8.5 | 6.1 | 1.60 | 16/0/25 |
| 5 | ema_cross | 50.00 | 5.0 | 2.0 | 41 | 66% | +8.5 | 6.1 | 1.60 | 16/0/25 |
| 6 | ema_cross | 50.00 | 5.0 | 3.0 | 41 | 66% | +8.5 | 6.1 | 1.60 | 16/0/25 |
| 7 | ema_cross | 10.00 | 5.0 | 1.5 | 41 | 54% | +8.4 | 6.1 | 1.59 | 16/0/25 |
| 8 | ema_cross | 10.00 | 5.0 | 2.0 | 41 | 54% | +8.4 | 6.1 | 1.59 | 16/0/25 |
| 9 | ema_cross | 10.00 | 5.0 | 3.0 | 41 | 54% | +8.4 | 6.1 | 1.59 | 16/0/25 |
| 10 | ema_cross | 50.00 | 5.0 | 1.5 | 41 | 54% | +8.4 | 6.1 | 1.59 | 16/0/25 |
| 11 | ema_cross | 50.00 | 5.0 | 2.0 | 41 | 54% | +8.4 | 6.1 | 1.59 | 16/0/25 |
| 12 | ema_cross | 50.00 | 5.0 | 3.0 | 41 | 54% | +8.4 | 6.1 | 1.59 | 16/0/25 |
| 13 | ema_cross | 10.00 | 5.0 | 1.5 | 41 | 61% | +7.8 | 6.1 | 1.55 | 16/0/25 |
| 14 | ema_cross | 10.00 | 5.0 | 2.0 | 41 | 61% | +7.8 | 6.1 | 1.55 | 16/0/25 |
| 15 | ema_cross | 10.00 | 5.0 | 3.0 | 41 | 61% | +7.8 | 6.1 | 1.55 | 16/0/25 |
| 16 | ema_cross | 50.00 | 5.0 | 1.5 | 41 | 61% | +7.8 | 6.1 | 1.55 | 16/0/25 |
| 17 | ema_cross | 50.00 | 5.0 | 2.0 | 41 | 61% | +7.8 | 6.1 | 1.55 | 16/0/25 |
| 18 | ema_cross | 50.00 | 5.0 | 3.0 | 41 | 61% | +7.8 | 6.1 | 1.55 | 16/0/25 |
| 19 | ema_cross | 5.00 | 5.0 | 1.5 | 41 | 66% | +7.2 | 5.2 | 1.60 | 16/0/25 |
| 20 | ema_cross | 5.00 | 5.0 | 2.0 | 41 | 66% | +7.2 | 5.2 | 1.60 | 16/0/25 |

## Key Findings

- **Most profitable combos**: ema_cross (318)
- **Best risk level**: 0.50% (84 profitable combos)

---

_Generated by `scripts/research/run_mega_sweep.py`._
_Strategies: rsi, ema_cross, bb, supertrend, regime_switch, donchian, macd, stochastic, vol_breakout, williams._
_Spot-long-only, single position, 0.1% taker fee each side, compounding equity._
_Regime: BULL (close > EMA200 + slope > 0), BEAR (close < EMA200 + slope < 0), RANGE (else)._
_IMPORTANT: This uses REAL KuCoin 5-year OHLCV data._
