# Strategy Candidate Matrix — kucoin-lane $110 Micro-Account Bot

> Last updated: 2026-06-02  
> Key constraints: KuCoin 0.1% taker/maker per side (round-trip 0.2%), min_funds = $0.10, $110 capital, max 2 concurrent positions @ $50 each, SPOT LONG-ONLY, BTC/USDT + ETH/USDT. Requires >0.35% total friction clearance per trade. Low trade frequency preferred.

---

| Strategy | Source | Timeframe | Fee-Aware | $110 Suitable | Trade Frequency | Expected Edge | Risk Level | Score | Verdict |
|----------|--------|-----------|-----------|---------------|-----------------|---------------|------------|-------|---------|
| PSAR Trailing Stop | our new implementation | 1h / 4h | Yes (trailing stops lock in gains) | Yes ($50 min) | Low | Medium | Low-Medium | 4.18 | ADOPT |
| FixedRiskRewardLoss | freqtrade pattern | 1h / 4h | Yes (break-even minimizes fees) | Yes ($50 min) | Low | Medium | Low | 4.00 | ADOPT |
| BreakEven | freqtrade-strategies | 1h / 4h | Yes (SL→breakeven reduces held loss) | Yes | Low | Medium | Medium | 3.82 | ADOPT |
| Supertrend Triple Confirmation | freqtrade pattern | 1h / 4h | Partial (fewer trades) | Yes | Very Low | High | Medium | 3.55 | EVALUATE |
| BbandRsi | freqtrade-strategies | 1h / 4h | Partial | Yes | Low | Medium | Medium | 3.45 | EVALUATE |
| Strategy002 | freqtrade-strategies | 1h / 4h | Partial | Partial | Medium | Medium | Medium | 3.36 | EVALUATE |
| Strategy005 | freqtrade-strategies | 1h / 4h | Partial | Partial | Medium | Medium-High | Medium-High | 3.18 | EVALUATE |
| CombinedBinHAndCluc | freqtrade-strategies | 5m | No | No | High | Low | High | 3.18 | SKIP |
| Wilder RSI + Signal | our improved RSI | 1h / 4h | No | Partial | Medium | Low | Medium-High | 3.09 | EVALUATE |
| Sample Strategy | freqtrade built-in | variable | No | No | variable | Low | High | 2.55 | SKIP |

---

## Scoring Rubric

Each category scored 1–5, weighted as follows:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Fee-awareness | 3x | Accounts for or minimizes round-trip friction |
| $110 suitability | 3x | Works at micro scale? Low min notional? |
| Signal quality | 2x | Avoids false signals? Has confirmation? |
| Risk management | 2x | Has proper SL/trailing stop/DCA? |
| Simplicity | 1x | Can be implemented without complex dependencies? |

**Score formula:** `(fee_awareness*3 + $110_suitability*3 + signal_quality*2 + risk_management*2 + simplicity*1) / 11`

Max possible = 5.00.

---

## Strategy Notes

### ADOPT

#### PSAR Trailing Stop
- **Source:** our new implementation
- **Why adopt:** PSAR is designed for trend following; trailing stop quantifies as fees are recouped incrementally. Low trade frequency suits micro-account. Works on BTC/ETH 4h trends.
- **Risk:** Whipsaws in sideways markets; mitigated with multi-timeframe filter.

#### FixedRiskRewardLoss
- **Source:** freqtrade pattern
- **Why adopt:** ATR-based stop, automatic break-even shift, and fixed TP create a mechanical risk/reward. Break-even feature directly minimizes fee drag on small trades.
- **Risk:** ATR can widen in volatility, increasing SL distance.

#### BreakEven
- **Source:** freqtrade-strategies
- **Why adopt:** Minimal ROI/break-even logic keeps losses small; easy to backtest.
- **Risk:** Break-even triggers can be hit by noise, giving back gains.

### EVALUATE

#### Supertrend Triple Confirmation
- Multi-timeframe confirmation reduces false signals. Built-in SL. Very low frequency.
- Concern: may miss entries; needs tuning.

#### BbandRsi
- Classic mean-reversion entry; low complexity. Needs confirmation to avoid whipsaws.

#### Strategy002 (BB+RSI+Stoch)
- Triple confirmation helps, but 1h/4h signals may be sparse. Moderate complexity.

#### Strategy005 (EMA+MACD+RSI hyperopt)
- Hyperopt parameters can overfit. May need larger datasets than available at micro scale.

#### Wilder RSI + Signal
- Our improved RSI could add edge, but mean-reversion in trending crypto markets risks losses.

### SKIP

#### CombinedBinHAndCluc
- 5m timeframe generates too many trades for $110; fees dominate.

#### Sample Strategy
- Freqtrade built-in is a template, not production-ready; no fee awareness.

---

## Risk Disclosure

Cryptocurrency trading involves substantial risk of loss. No strategy guarantees profit. All scores are subjective estimates based on backtest potential, not realized returns. Past performance does not indicate future results. Only allocate risk capital you can afford to lose.
