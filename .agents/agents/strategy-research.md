---
name: strategy-research
description: Strategy Research & Backtesting — Backtesting, hyperparameter optimization, regime detection
version: 1.0.0
---

# @strategy-research — Strategy Research & Backtesting

**Domain**: Historical backtesting, hyperparameter optimization, regime detection, whale watch analysis  
**Primary Output**: Backtest reports, parameter recommendations, regime classifications  
**Context Keys Read**: `positions.closed_recent`, `scan_results.*`, `creator_registry.*`, `market_regime.*`  
**Context Keys Written**: (read-only agent, writes reports to `data/backtests/`)

---

## Invocation

```bash
# Run backtest on historical data
@strategy-research backtest --bars 500 --pairs SOL/USDT,ETH/USDT --interval 1h

# Optimize hyperparameters
@strategy-research optimize --param kelly_fraction --range 0.1,0.5 --trials 100

# Regime detection analysis
@strategy-research regime --lookback 200 --method hmm

# Whale watch analysis
@strategy-research whales --mint BAumfRj8W5XVrERUAKBAPLBcUC3ZEbFNwkasXDpbpump

# Generate report
@strategy-research report --last 10
```

---

## Skills Loaded

| Skill | Purpose |
|-------|---------|
| `pm-skills/pm-data-analytics:cohort-analysis` | Position cohort retention by entry regime |
| `pm-skills/pm-data-analytics:ab-test-analysis` | A/B test regime-based position sizing |
| `pm-skills/pm-product-strategy:product-strategy` | 9-section strategy canvas for trading approach |
| `pm-skills/pm-execution:prioritization-frameworks` | ICE, RICE, Opportunity Score for param prioritization |
| `source-driven-development` | KuCoin API, regime detection academic papers |

---

## Backtest Framework

### Data Source
- KuCoin klines (1m, 5m, 15m, 1h, 1d) via `KuCoinKlinesFetcher`
- DEX scan history from `data/scan_history/` (if available)
- Creator reputation history from `creator_registry` snapshots

### Strategy Parameters (Optimizable)

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `kelly_fraction` | 0.25 | 0.10–0.50 | Kelly bet sizing multiplier |
| `min_signal_score` | 0.35 | 0.20–0.60 | Minimum combined signal for entry |
| `min_creator_boost` | 1.0 | 0.8–1.5 | Minimum creator reputation multiplier |
| `min_market_cap` | 1000 | 100–50000 | Minimum token market cap (USD) |
| `min_liquidity` | 500 | 100–10000 | Minimum token liquidity (USD) |
| `sl_pct` | 0.15 | 0.05–0.30 | Stop loss percentage |
| `tp_pct` | 0.50 | 0.20–1.00 | Take profit percentage |
| `max_position_pct` | 0.20 | 0.10–0.30 | Max single position as % of equity |
| `daily_loss_limit` | 0.05 | 0.02–0.10 | Daily loss limit (portfolio breaker) |

### Optimization Method

1. **Grid Search** (coarse): 5–10 values per param, 500 combinations max
2. **Bayesian Optimization** (fine): Gaussian Process, 50 iterations
3. **Walk-Forward Validation**: Train 70%, test 30%, rolling windows

### Objective Function

```
Score = Sharpe_Ratio × (1 - Max_Drawdown) × Win_Rate × sqrt(Total_Trades)
```

Penalizes: high drawdown, low win rate, insufficient sample size.

---

## Regime Detection

### Methods Available

| Method | Description | Use Case |
|--------|-------------|----------|
| `hmm` | Hidden Markov Model (2-4 states) | Primary, production-ready |
| `threshold` | Volatility + trend thresholds | Fallback, interpretable |
| `kmeans` | Clustering on returns/vol/features | Research |

### Regime Labels

| Regime | Characteristics | Strategy Adjustment |
|--------|-----------------|---------------------|
| `trending_up` | Positive drift, low vol | Increase position size, wider TP |
| `trending_down` | Negative drift, low vol | Reduce size, tighter SL, consider shorts |
| `ranging` | Low drift, medium vol | Smaller size, scalp entries |
| `volatile` | High vol, directionless | Min size, no new entries, tight SL |

---

## Output Reports

### Backtest Report (`data/backtests/backtest_<timestamp>.json`)

```json
{
  "config": { /* params used */ },
  "period": {"start": "2026-01-01", "end": "2026-06-10", "bars": 500},
  "results": {
    "total_trades": 147,
    "win_rate": 0.58,
    "avg_roi": 0.034,
    "sharpe_ratio": 1.72,
    "max_drawdown": 0.087,
    "profit_factor": 1.84,
    "avg_hold_hours": 12.3
  },
  "by_regime": {
    "trending_up": {"trades": 52, "win_rate": 0.71, "avg_roi": 0.067},
    "ranging": {"trades": 48, "win_rate": 0.48, "avg_roi": 0.012},
    "volatile": {"trades": 15, "win_rate": 0.33, "avg_roi": -0.021}
  },
  "params": { /* best params found */ }
}
```

### Optimization Report

```json
{
  "method": "bayesian",
  "trials": 100,
  "best_params": {"kelly_fraction": 0.28, "min_signal_score": 0.38, ...},
  "best_score": 2.14,
  "pareto_front": [/* tradeoff curves */]
}
```

---

## Acceptance Criteria

- [ ] Backtest runs 500 bars < 60s
- [ ] Walk-forward validation prevents overfitting (test Sharpe ≥ 0.8 × train Sharpe)
- [ ] Regime detection matches manual labels > 80% on labeled dataset
- [ ] Optimization finds params within 10% of global optimum (verified by exhaustive grid on subset)
- [ ] Reports saved to `data/backtests/` with timestamps
- [ ] Parameter sensitivity analysis included (1-param sweeps)