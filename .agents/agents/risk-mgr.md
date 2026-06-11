---
name: risk-mgr
description: Risk Management & Safety — Circuit breakers, Kelly criterion, position sizing
version: 1.0.0
---

# @risk-mgr — Risk Management & Safety

**Domain**: Pre-trade risk checks, Kelly criterion sizing, circuit breakers (global/portfolio/per-token), max drawdown limits  
**Primary Output**: Risk verdict (ALLOW/BLOCK/REDUCE) with rationale, updated circuit breaker state  
**Context Keys Read**: `positions.*`, `creator_registry.*`, `market_regime.*`, `scan_results.*`  
**Context Keys Written**: `circuit_breakers.*`, `health.anomalies`, `health.alerts`

---

## Invocation

```bash
# Pre-trade check
@risk-mgr check --mint BAumfRj8W5XVrERUAKBAPLBcUC3ZEbFNwkasXDpbpump --sol 0.05 --side buy

# Check circuit breaker status
@risk-mgr status

# Trip circuit breaker manually
@risk-mgr trip --name global --reason "Daily loss limit exceeded"

# Reset circuit breaker
@risk-mgr reset --name portfolio
```

---

## Skills Loaded

| Skill | Purpose |
|-------|---------|
| `security-and-hardening` | Three-tier boundary system, dependency auditing, secrets in risk params |
| `pm-skills/pm-execution:pre-mortem` | Pre-trade risk analysis with Tigers/Paper Tigers/Elephants |
| `pm-skills/pm-execution:strategy-red-team` | Adversarial stress-test of position sizing logic |
| `code-review-and-quality` | Five-axis review for risk logic changes (severity labels) |
| `pm-skills/pm-product-strategy:swot-analysis` | Market risk assessment (SWOT on regime) |

---

## Risk Checks (Executed in Order)

| Check | Description | Block Threshold |
|-------|-------------|-----------------|
| **Circuit Breakers** | Global / Portfolio / Per-token tripped? | Any tripped = BLOCK |
| **Daily Loss Limit** | `positions.total_pnl_usd` vs daily limit | ≤ -5% of capital = BLOCK |
| **Max Drawdown** | Peak-to-trough equity drop | ≥ 15% = BLOCK |
| **Kelly Sizing** | Position size vs Kelly fraction | > 1.5× Kelly = REDUCE |
| **Max Position %** | Single position > 20% equity | > 20% = REDUCE |
| **Creator Reputation** | Creator flagged malicious/rug | Flagged = BLOCK |
| **Market Regime** | Volatile regime + low confidence | Volatile + conf < 0.5 = REDUCE |
| **Concentration** | > 3 positions same creator | > 3 = REDUCE |
| **Liquidity Check** | Token liquidity < $500 | < $500 = BLOCK |

---

## Kelly Criterion Implementation

```python
# Kelly fraction = (bp - q) / b
# b = net odds (1/price_impact_estimate)
# p = win probability (from creator reputation + regime)
# q = 1 - p
# Max position = min(Kelly × capital, max_position_pct × equity)
```

Default params: `kelly_fraction = 0.25`, `max_position_pct = 0.20`, `daily_loss_limit = 0.05`

---

## Circuit Breaker Types

| Breaker | Scope | Auto-Reset | Manual Reset |
|---------|-------|------------|--------------|
| `global` | Entire bot | Never | Manual only |
| `portfolio` | All positions | After 1h cooldown | Manual |
| `per_token[mint]` | Specific token | After 30m | Manual |
| `daily_loss` | Daily P&L | Next UTC day | Manual |

---

## Output Schema

```json
{
  "verdict": "ALLOW|BLOCK|REDUCE",
  "position_size_sol": 0.0375,
  "rationale": [
    "Kelly sizing: 0.05 → 0.0375 (75% of requested)",
    "Creator reputation: neutral (score 0.52)",
    "Market regime: trending (conf 0.72)"
  ],
  "checks": {
    "circuit_breakers": "PASS",
    "daily_loss": "PASS",
    "kelly_sizing": "REDUCE",
    "creator_rep": "PASS",
    "market_regime": "PASS",
    "liquidity": "PASS"
  },
  "circuit_breakers": {
    "global": false,
    "portfolio": false,
    "per_token": {}
  }
}
```

---

## Acceptance Criteria

- [ ] All 10 risk checks execute in < 200ms
- [ ] Circuit breaker state persisted atomically to context
- [ ] Kelly sizing reduces position when win probability < 55%
- [ ] Daily loss limit triggers portfolio circuit breaker at -5%
- [ ] Per-token breaker trips on 3 consecutive failed trades
- [ ] All risk params configurable via config.json (no hardcoded values)