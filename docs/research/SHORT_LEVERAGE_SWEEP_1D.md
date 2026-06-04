# Short + Leverage Mega Sweep — 5-Year BTC/USDT Daily

- **Data**: `data/btc_usdt_1d.csv` (1824.0 days, ~5 years)
- **Start equity**: $110.00
- **Leverages tested**: 1,2,3,5
- **Short modes**: True,False
- **Fee modes**: futures_taker,futures_maker
- **Total combos**: 368,640
- **Qualified (>=8 trades)**: 262,080
- **Profitable (net > 0)**: 223,884 (85.4%)

## 1. Executive Summary: Leverage × Short × Fee

| Leverage | Short | Fee Mode | Combos | Profitable | Profit% | Best Net% | Avg Net% | Avg MaxDD% | Liquidations |
|:--------:|:-----:|:--------:|-------:|:----------:|:-------:|:--------:|:--------:|:----------:|:------------:|
| 1x | no | futures_maker | 16,380 | 13,938 | 85.1 | +88.2 | +7.5 | 3.7 | 0 |
| 1x | no | futures_taker | 16,380 | 13,545 | 82.7 | +84.0 | +6.7 | 3.9 | 0 |
| 1x | YES | futures_maker | 16,380 | 14,823 | 90.5 | +158.9 | +11.1 | 3.2 | 0 |
| 1x | YES | futures_taker | 16,380 | 14,445 | 88.2 | +144.3 | +10.2 | 3.3 | 0 |
| 2x | no | futures_maker | 16,380 | 13,546 | 82.7 | +187.4 | +9.4 | 4.5 | 0 |
| 2x | no | futures_taker | 16,380 | 13,103 | 80.0 | +159.1 | +8.2 | 4.7 | 0 |
| 2x | YES | futures_maker | 16,380 | 14,745 | 90.0 | +421.6 | +14.8 | 3.8 | 0 |
| 2x | YES | futures_taker | 16,380 | 14,349 | 87.6 | +375.7 | +13.6 | 4.0 | 0 |
| 3x | no | futures_maker | 16,380 | 13,541 | 82.7 | +249.1 | +10.4 | 4.6 | 0 |
| 3x | no | futures_taker | 16,380 | 13,096 | 80.0 | +210.8 | +9.1 | 4.9 | 0 |
| 3x | YES | futures_maker | 16,380 | 14,742 | 90.0 | +517.6 | +16.1 | 4.0 | 0 |
| 3x | YES | futures_taker | 16,380 | 14,346 | 87.6 | +453.3 | +14.7 | 4.2 | 0 |
| 5x | no | futures_maker | 16,380 | 13,511 | 82.5 | +249.1 | +10.4 | 4.6 | 45 |
| 5x | no | futures_taker | 16,380 | 13,066 | 79.8 | +210.8 | +9.1 | 4.9 | 45 |
| 5x | YES | futures_maker | 16,380 | 14,742 | 90.0 | +517.6 | +16.1 | 4.0 | 0 |
| 5x | YES | futures_taker | 16,380 | 14,346 | 87.6 | +453.3 | +14.7 | 4.2 | 0 |

## 2. Short vs Long-Only Comparison (same params)

For each (strategy, risk, SL, leverage, fee), compare allow_short=False vs True:

| Metric | Long-Only | Short Enabled | Delta |
|--------|:---------:|:-------------:|:-----:|
| Avg Net% | +8.9 | +13.9 | +5.1 |
| Best Net% | +249.1 | +517.6 | +268.5 |
| Avg Win Rate | 62.1% | 60.0% | -2.1% |
| Avg MaxDD% | 4.5 | 3.8 | -0.6 |
| Total Liquidations | 90 | 0 | -90 |

## 3. Per-Leverage Breakdown

| Leverage | Combos | Profitable | Profit% | Best Net% | Worst Net% | Avg Net% | Avg MaxDD% | Avg Liquidations |
|:--------:|-------:|:----------:|:-------:|:---------:|:----------:|:--------:|:----------:|:----------------:|
| 1x | 65,520 | 56,751 | 86.6 | +158.9 | -18.5 | +8.9 | 3.5 | 0.00 |
| 2x | 65,520 | 55,743 | 85.1 | +421.6 | -22.8 | +11.5 | 4.3 | 0.00 |
| 3x | 65,520 | 55,725 | 85.1 | +517.6 | -22.8 | +12.6 | 4.4 | 0.00 |
| 5x | 65,520 | 55,665 | 85.0 | +517.6 | -22.8 | +12.6 | 4.4 | 0.00 |

## 4. Regime Analysis with Shorts

### LONG-ONLY

| Strategy | Bull Avg PnL/trade | Bear Avg PnL/trade | Range Avg PnL/trade | Short Trades | Short PnL% | Long PnL% |
|----------|:------------------:|:------------------:|:-------------------:|:------------:|:----------:|:----------:|
| bb | +1.475 | +0.088 | +2.416 | 0 | +0.0 | +107326.2 |
| ema_cross | +1.926 | +1.305 | -0.632 | 0 | +0.0 | +118671.8 |
| macd | +1.062 | +0.258 | -0.485 | 0 | +0.0 | +56232.0 |
| regime_switch | +2.794 | -0.768 | -3.714 | 0 | +0.0 | +241355.2 |
| rsi | +1.855 | +1.177 | -0.644 | 0 | +0.0 | +1303596.2 |
| stochastic | -1.686 | +1.036 | -0.142 | 0 | +0.0 | -3520.7 |
| supertrend | +2.454 | +1.616 | +0.897 | 0 | +0.0 | +566966.1 |
| vol_breakout | +1.615 | +2.543 | -0.134 | 0 | +0.0 | +2283512.2 |
| williams | +1.195 | -0.196 | +1.022 | 0 | +0.0 | +60672.9 |

### SHORT ENABLED

| Strategy | Bull Avg PnL/trade | Bear Avg PnL/trade | Range Avg PnL/trade | Short Trades | Short PnL% | Long PnL% |
|----------|:------------------:|:------------------:|:-------------------:|:------------:|:----------:|:----------:|
| bb | +1.475 | +8.619 | +2.416 | 41,760 | +359917.4 | +103640.5 |
| ema_cross | +1.926 | -1.816 | -0.632 | 34,560 | -62768.0 | +73575.6 |
| macd | +1.062 | +0.134 | -0.485 | 33,120 | +4449.2 | +47680.8 |
| regime_switch | +2.794 | +2.726 | -3.714 | 298,080 | +812589.6 | +470258.4 |
| rsi | +1.855 | +3.852 | -0.644 | 680,400 | +2621082.0 | +502578.9 |
| stochastic | -1.686 | +3.669 | -0.142 | 33,120 | +121505.3 | -37845.8 |
| supertrend | +2.454 | -0.262 | +0.897 | 106,560 | -27932.7 | +394738.9 |
| vol_breakout | +1.615 | +0.328 | -0.134 | 369,360 | +121333.4 | +1338635.5 |
| williams | +1.195 | +3.786 | +1.022 | 72,000 | +272583.4 | +74497.7 |

## 5. Liquidation Analysis

| Leverage | Combos w/ Liquidations | Avg Liquidations | Max Liquidations | Avg Net% (w/ liq) | Avg Net% (no liq) |
|:--------:|:---------------------:|:----------------:|:----------------:|:-----------------:|:-----------------:|
| 1x | 0 | 0.00 | 0 | +0.0 | +8.9 |
| 2x | 0 | 0.00 | 0 | +0.0 | +11.5 |
| 3x | 0 | 0.00 | 0 | +0.0 | +12.6 |
| 5x | 90 | 0.00 | 1 | -4.4 | +12.6 |

## 6. Top 20 Overall Configs

| # | Strategy | Lev | Short | Fee | Risk% | SL% | R:R | Trades | WR | Net% | MaxDD% | PF | Liq | L/S PnL | Bull/Bear/Range |
|---|----------|:---:|:-----:|:---:|------:|----:|----:|-------:|---:|-----:|-------:|---:|:---:|:-------:|:--------------:|
| 1 | williams | 3x | Y | futures_maker | 5.00 | 1.5 | 1.5 | 96 | 56% | +517.6 | 9.8 | 3.70 | 0 | +99/+213 | 34/50/12 |
| 2 | williams | 3x | Y | futures_maker | 5.00 | 1.5 | 2.0 | 96 | 56% | +517.6 | 9.8 | 3.70 | 0 | +99/+213 | 34/50/12 |
| 3 | williams | 3x | Y | futures_maker | 5.00 | 1.5 | 3.0 | 96 | 56% | +517.6 | 9.8 | 3.70 | 0 | +99/+213 | 34/50/12 |
| 4 | williams | 5x | Y | futures_maker | 5.00 | 1.5 | 1.5 | 96 | 56% | +517.6 | 9.8 | 3.70 | 0 | +165/+355 | 34/50/12 |
| 5 | williams | 5x | Y | futures_maker | 5.00 | 1.5 | 2.0 | 96 | 56% | +517.6 | 9.8 | 3.70 | 0 | +165/+355 | 34/50/12 |
| 6 | williams | 5x | Y | futures_maker | 5.00 | 1.5 | 3.0 | 96 | 56% | +517.6 | 9.8 | 3.70 | 0 | +165/+355 | 34/50/12 |
| 7 | williams | 3x | Y | futures_maker | 5.00 | 1.5 | 1.5 | 96 | 51% | +492.9 | 10.4 | 3.63 | 0 | +96/+208 | 34/50/12 |
| 8 | williams | 3x | Y | futures_maker | 5.00 | 1.5 | 2.0 | 96 | 51% | +492.9 | 10.4 | 3.63 | 0 | +96/+208 | 34/50/12 |
| 9 | williams | 3x | Y | futures_maker | 5.00 | 1.5 | 3.0 | 96 | 51% | +492.9 | 10.4 | 3.63 | 0 | +96/+208 | 34/50/12 |
| 10 | williams | 5x | Y | futures_maker | 5.00 | 1.5 | 1.5 | 96 | 51% | +492.9 | 10.4 | 3.63 | 0 | +159/+347 | 34/50/12 |
| 11 | williams | 5x | Y | futures_maker | 5.00 | 1.5 | 2.0 | 96 | 51% | +492.9 | 10.4 | 3.63 | 0 | +159/+347 | 34/50/12 |
| 12 | williams | 5x | Y | futures_maker | 5.00 | 1.5 | 3.0 | 96 | 51% | +492.9 | 10.4 | 3.63 | 0 | +159/+347 | 34/50/12 |
| 13 | williams | 3x | Y | futures_taker | 5.00 | 1.5 | 1.5 | 96 | 70% | +453.3 | 10.6 | 3.41 | 0 | +91/+202 | 34/50/12 |
| 14 | williams | 3x | Y | futures_taker | 5.00 | 1.5 | 2.0 | 96 | 70% | +453.3 | 10.6 | 3.41 | 0 | +91/+202 | 34/50/12 |
| 15 | williams | 3x | Y | futures_taker | 5.00 | 1.5 | 3.0 | 96 | 70% | +453.3 | 10.6 | 3.41 | 0 | +91/+202 | 34/50/12 |
| 16 | williams | 5x | Y | futures_taker | 5.00 | 1.5 | 1.5 | 96 | 70% | +453.3 | 10.6 | 3.41 | 0 | +151/+337 | 34/50/12 |
| 17 | williams | 5x | Y | futures_taker | 5.00 | 1.5 | 2.0 | 96 | 70% | +453.3 | 10.6 | 3.41 | 0 | +151/+337 | 34/50/12 |
| 18 | williams | 5x | Y | futures_taker | 5.00 | 1.5 | 3.0 | 96 | 70% | +453.3 | 10.6 | 3.41 | 0 | +151/+337 | 34/50/12 |
| 19 | williams | 3x | Y | futures_taker | 5.00 | 1.5 | 1.5 | 96 | 69% | +436.8 | 11.1 | 3.36 | 0 | +88/+199 | 34/50/12 |
| 20 | williams | 3x | Y | futures_taker | 5.00 | 1.5 | 2.0 | 96 | 69% | +436.8 | 11.1 | 3.36 | 0 | +88/+199 | 34/50/12 |

## 7. Account Threshold Recommendations

Based on liquidation and drawdown analysis across leverage levels:

### 1x Leverage
- Best config: williams risk=5.00% SL=1.5%
- Net: +158.9%, MaxDD: 5.6%, Liquidations: 0
- Short trades: 50, Short PnL: +70.9%
- Recommended minimum equity: $5

### 2x Leverage
- Best config: williams risk=5.00% SL=1.5%
- Net: +421.6%, MaxDD: 9.8%, Liquidations: 0
- Short trades: 50, Short PnL: +141.9%
- Recommended minimum equity: $10

### 3x Leverage
- Best config: williams risk=5.00% SL=1.5%
- Net: +517.6%, MaxDD: 9.8%, Liquidations: 0
- Short trades: 50, Short PnL: +212.8%
- Recommended minimum equity: $15

### 5x Leverage
- Best config: williams risk=5.00% SL=1.5%
- Net: +517.6%, MaxDD: 9.8%, Liquidations: 0
- Short trades: 50, Short PnL: +354.7%
- Recommended minimum equity: $25

---

_Generated by `scripts/research/run_short_leverage_sweep.py`._
_Strategies: vol_breakout,supertrend,rsi,bb,williams,macd,donchian,stochastic,ema_cross,regime_switch_
_Leverages: 1,2,3,5_
_Short modes: True,False_
_Fee modes: futures_taker,futures_maker_
_KuCoin USDT-M futures: 0.02% maker / 0.06% taker, 0.4% maint margin, avg 0.03%/day funding._
_Regime: BULL (close > EMA200 + slope > 0), BEAR (close < EMA200 + slope < 0), RANGE (else)._
_IMPORTANT: This uses REAL KuCoin 5-year OHLCV data on DAILY timeframe._
_Short positions are regime-aware: SHORT in BEAR, LONG in BULL/RANGE._
_Leverage applies to both long and short positions; liquidation checked each bar._
