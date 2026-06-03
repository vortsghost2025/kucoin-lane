# Short + Leverage Mega Sweep — 5-Year BTC/USDT Daily

- **Data**: `data/btc_usdt_1d.csv` (1824.0 days, ~5 years)
- **Start equity**: $110.00
- **Leverages tested**: 1,2,3,5,10
- **Short modes**: True,False
- **Fee modes**: futures_taker,futures_maker
- **Total combos**: 93,600
- **Qualified (>=8 trades)**: 93,600
- **Profitable (net > 0)**: 80,493 (86.0%)

## 1. Executive Summary: Leverage × Short × Fee

| Leverage | Short | Fee Mode | Combos | Profitable | Profit% | Best Net% | Avg Net% | Avg MaxDD% | Liquidations |
|:--------:|:-----:|:--------:|-------:|:----------:|:-------:|:--------:|:--------:|:----------:|:------------:|
| 1x | no | futures_maker | 4,680 | 4,650 | 99.4 | +88.2 | +15.7 | 4.6 | 0 |
| 1x | no | futures_taker | 4,680 | 4,650 | 99.4 | +84.0 | +14.3 | 4.9 | 0 |
| 1x | YES | futures_maker | 4,680 | 3,966 | 84.7 | +90.2 | +10.7 | 4.4 | 0 |
| 1x | YES | futures_taker | 4,680 | 3,657 | 78.1 | +85.1 | +9.4 | 4.7 | 0 |
| 2x | no | futures_maker | 4,680 | 4,650 | 99.4 | +187.4 | +20.1 | 5.4 | 0 |
| 2x | no | futures_taker | 4,680 | 4,650 | 99.4 | +159.1 | +18.3 | 5.7 | 0 |
| 2x | YES | futures_maker | 4,680 | 3,921 | 83.8 | +206.1 | +14.2 | 5.2 | 0 |
| 2x | YES | futures_taker | 4,680 | 3,582 | 76.5 | +174.8 | +12.4 | 5.5 | 0 |
| 3x | no | futures_maker | 4,680 | 4,650 | 99.4 | +249.1 | +21.9 | 5.4 | 0 |
| 3x | no | futures_taker | 4,680 | 4,650 | 99.4 | +210.8 | +19.8 | 5.7 | 0 |
| 3x | YES | futures_maker | 4,680 | 3,921 | 83.8 | +266.9 | +15.5 | 5.4 | 0 |
| 3x | YES | futures_taker | 4,680 | 3,582 | 76.5 | +225.3 | +13.7 | 5.7 | 0 |
| 5x | no | futures_maker | 4,680 | 4,620 | 98.7 | +249.1 | +21.9 | 5.4 | 45 |
| 5x | no | futures_taker | 4,680 | 4,620 | 98.7 | +210.8 | +19.8 | 5.8 | 45 |
| 5x | YES | futures_maker | 4,680 | 3,921 | 83.8 | +266.9 | +15.5 | 5.4 | 0 |
| 5x | YES | futures_taker | 4,680 | 3,582 | 76.5 | +225.3 | +13.7 | 5.7 | 0 |
| 10x | no | futures_maker | 4,680 | 4,023 | 86.0 | +112.9 | +9.0 | 11.6 | 8,865 |
| 10x | no | futures_taker | 4,680 | 3,744 | 80.0 | +89.0 | +7.2 | 12.0 | 8,865 |
| 10x | YES | futures_maker | 4,680 | 2,769 | 59.2 | +169.0 | +5.8 | 10.9 | 6,885 |
| 10x | YES | futures_taker | 4,680 | 2,685 | 57.4 | +138.1 | +4.0 | 11.4 | 6,885 |

## 2. Short vs Long-Only Comparison (same params)

For each (strategy, risk, SL, leverage, fee), compare allow_short=False vs True:

| Metric | Long-Only | Short Enabled | Delta |
|--------|:---------:|:-------------:|:-----:|
| Avg Net% | +16.8 | +11.5 | -5.3 |
| Best Net% | +249.1 | +266.9 | +17.9 |
| Avg Win Rate | 67.2% | 55.7% | -11.5% |
| Avg MaxDD% | 6.7 | 6.4 | -0.2 |
| Total Liquidations | 17,820 | 13,770 | -4,050 |

## 3. Per-Leverage Breakdown

| Leverage | Combos | Profitable | Profit% | Best Net% | Worst Net% | Avg Net% | Avg MaxDD% | Avg Liquidations |
|:--------:|-------:|:----------:|:-------:|:---------:|:----------:|:--------:|:----------:|:----------------:|
| 1x | 18,720 | 16,923 | 90.4 | +90.2 | -9.6 | +12.5 | 4.6 | 0.00 |
| 2x | 18,720 | 16,803 | 89.8 | +206.1 | -9.7 | +16.2 | 5.5 | 0.00 |
| 3x | 18,720 | 16,803 | 89.8 | +266.9 | -9.7 | +17.7 | 5.5 | 0.00 |
| 5x | 18,720 | 16,743 | 89.4 | +266.9 | -13.7 | +17.7 | 5.6 | 0.00 |
| 10x | 18,720 | 13,221 | 70.6 | +169.0 | -29.6 | +6.5 | 11.5 | 1.68 |

## 4. Regime Analysis with Shorts

### LONG-ONLY

| Strategy | Bull Avg PnL/trade | Bear Avg PnL/trade | Range Avg PnL/trade | Short Trades | Short PnL% | Long PnL% |
|----------|:------------------:|:------------------:|:-------------------:|:------------:|:----------:|:----------:|
| supertrend | +2.554 | +1.956 | +1.369 | 0 | +0.0 | +799120.8 |
| vol_breakout | +1.591 | +3.441 | -0.204 | 0 | +0.0 | +3235908.4 |

### SHORT ENABLED

| Strategy | Bull Avg PnL/trade | Bear Avg PnL/trade | Range Avg PnL/trade | Short Trades | Short PnL% | Long PnL% |
|----------|:------------------:|:------------------:|:-------------------:|:------------:|:----------:|:----------:|
| supertrend | +2.554 | -0.431 | +1.369 | 133,200 | -57466.1 | +538636.4 |
| vol_breakout | +1.591 | +0.502 | -0.204 | 461,700 | +231636.5 | +1637792.8 |

## 5. Liquidation Analysis

| Leverage | Combos w/ Liquidations | Avg Liquidations | Max Liquidations | Avg Net% (w/ liq) | Avg Net% (no liq) |
|:--------:|:---------------------:|:----------------:|:----------------:|:-----------------:|:-----------------:|
| 1x | 0 | 0.00 | 0 | +0.0 | +12.5 |
| 2x | 0 | 0.00 | 0 | +0.0 | +16.2 |
| 3x | 0 | 0.00 | 0 | +0.0 | +17.7 |
| 5x | 90 | 0.00 | 1 | -4.4 | +17.8 |
| 10x | 18,000 | 1.68 | 4 | +6.4 | +8.0 |

## 6. Top 20 Overall Configs

| # | Strategy | Lev | Short | Fee | Risk% | SL% | R:R | Trades | WR | Net% | MaxDD% | PF | Liq | L/S PnL | Bull/Bear/Range |
|---|----------|:---:|:-----:|:---:|------:|----:|----:|-------:|---:|-----:|-------:|---:|:---:|:-------:|:--------------:|
| 1 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 1.5 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 2 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 1.5 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 3 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 1.5 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 4 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 1.5 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 5 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 1.5 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 6 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 1.5 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 7 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 2.0 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 8 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 2.0 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 9 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 2.0 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 10 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 2.0 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 11 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 2.0 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 12 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 2.0 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 13 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 3.0 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 14 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 3.0 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 15 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 3.0 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 16 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 3.0 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 17 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 3.0 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 18 | vol_breakout | 3x | Y | futures_maker | 5.00 | 1.5 | 3.0 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +146/+67 | 62/28/7 |
| 19 | vol_breakout | 5x | Y | futures_maker | 5.00 | 1.5 | 1.5 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +243/+111 | 62/28/7 |
| 20 | vol_breakout | 5x | Y | futures_maker | 5.00 | 1.5 | 1.5 | 97 | 53% | +266.9 | 16.0 | 2.44 | 0 | +243/+111 | 62/28/7 |

## 7. Account Threshold Recommendations

Based on liquidation and drawdown analysis across leverage levels:

### 1x Leverage
- Best config: vol_breakout risk=2.00% SL=1.5%
- Net: +90.2%, MaxDD: 6.2%, Liquidations: 0
- Short trades: 28, Short PnL: +22.2%
- Recommended minimum equity: $5

### 2x Leverage
- Best config: vol_breakout risk=5.00% SL=1.5%
- Net: +206.1%, MaxDD: 16.0%, Liquidations: 0
- Short trades: 28, Short PnL: +44.5%
- Recommended minimum equity: $10

### 3x Leverage
- Best config: vol_breakout risk=5.00% SL=1.5%
- Net: +266.9%, MaxDD: 16.0%, Liquidations: 0
- Short trades: 28, Short PnL: +66.7%
- Recommended minimum equity: $15

### 5x Leverage
- Best config: vol_breakout risk=5.00% SL=1.5%
- Net: +266.9%, MaxDD: 16.0%, Liquidations: 0
- Short trades: 28, Short PnL: +111.2%
- Recommended minimum equity: $25

### 10x Leverage
- Best config: vol_breakout risk=5.00% SL=1.5%
- Net: +169.0%, MaxDD: 35.3%, Liquidations: 2
- Short trades: 28, Short PnL: +222.4%
- Recommended minimum equity: $50

---

_Generated by `scripts/research/run_short_leverage_sweep.py`._
_Strategies: vol_breakout,supertrend_
_Leverages: 1,2,3,5,10_
_Short modes: True,False_
_Fee modes: futures_taker,futures_maker_
_KuCoin USDT-M futures: 0.02% maker / 0.06% taker, 0.4% maint margin, avg 0.03%/day funding._
_Regime: BULL (close > EMA200 + slope > 0), BEAR (close < EMA200 + slope < 0), RANGE (else)._
_IMPORTANT: This uses REAL KuCoin 5-year OHLCV data on DAILY timeframe._
_Short positions are regime-aware: SHORT in BEAR, LONG in BULL/RANGE._
_Leverage applies to both long and short positions; liquidation checked each bar._
