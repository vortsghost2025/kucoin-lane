---
name: trader
description: Trading Execution Engine — Jupiter DEX paper, KuCoin margin, SL/TP monitoring
version: 1.0.0
---

# @trader — Trading Execution Engine

**Domain**: Order execution on Jupiter DEX (paper) and KuCoin margin (live), position monitoring with SL/TP auto-close  
**Primary Output**: Executed trade records with fill price, fees, P&L  
**Context Keys Read**: `scan_results.*`, `creator_registry.*`, `circuit_breakers.*`, `market_regime.*`  
**Context Keys Written**: `positions.*`, `health.api_latency.jupiter`, `health.api_latency.kucoin`

---

## Invocation

```bash
# Execute buy order
@trader execute --side buy --mint BAumfRj8W5XVrERUAKBAPLBcUC3ZEbFNwkasXDpbpump --sol 0.05 --sl 0.85 --tp 1.5

# Execute sell order
@trader execute --side sell --mint BAumfRj8W5XVrERUAKBAPLBcUC3ZEbFNwkasXDpbpump --amount 100%

# Monitor open positions (SL/TP check)
@trader monitor

# Get open positions
@trader positions
```

---

## Skills Loaded

| Skill | Purpose |
|-------|---------|
| `incremental-implementation` | Thin vertical slices: quote → sign → execute → confirm → record |
| `test-driven-development` | Red-Green-Refactor for order logic, slippage calc, fee estimation |
| `security-and-hardening` | API key handling, secret management, OWASP Top 10, three-tier boundary |
| `api-and-interface-design` | Contract-first Jupiter/KuCoin client design, Hyrum's Law |
| `pm-skills/pm-execution:test-scenarios` | Happy paths, edge cases, error handling for execution |

---

## Input/Output Schema

### Input
```json
{
  "action": "execute|monitor|positions",
  "side": "buy|sell",
  "mint": "BAumfRj8W5XVrERUAKBAPLBcUC3ZEbFNwkasXDpbpump",
  "sol": 0.05,
  "amount_pct": 100,
  "sl": 0.85,
  "tp": 1.5,
  "venue": "jupiter|kucoin"
}
```

### Output (written to context)
```json
{
  "success": true,
  "trade": {
    "id": "trade_20260610_153000_abc123",
    "mint": "BAumfRj8W5XVrERUAKBAPLBcUC3ZEbFNwkasXDpbpump",
    "side": "buy",
    "venue": "jupiter",
    "sol_in": 0.05,
    "tokens_out": 123456789,
    "price_sol": 0.000000405,
    "fee_sol": 0.000005,
    "slippage_bps": 15,
    "tx_sig": "5x7...",
    "sl_price": 0.000000344,
    "tp_price": 0.000000607,
    "executed_at": "2026-06-10T15:30:05Z"
  }
}
```

---

## Pre-Execution Checks (via @risk-mgr)

1. **Circuit Breakers**: `global`, `portfolio`, `per_token[mint]` all not tripped
2. **Kelly Sizing**: Position size ≤ Kelly fraction × available capital
3. **Creator Reputation**: Creator not flagged as malicious/serial rugger
4. **Market Regime**: Not in `volatile` regime with low confidence

---

## SL/TP Monitoring

- Runs every cycle via `@trader monitor`
- Fetches current price from Jupiter quote (token → SOL)
- Triggers market sell if price ≤ SL or ≥ TP
- Records P&L to context via `record_position_close()`

---

## Acceptance Criteria

- [ ] Jupiter paper execution returns realistic fill prices (within 50 bps of quote)
- [ ] KuCoin margin stubs return structured responses (ready for live keys)
- [ ] SL/TP triggers within 1 cycle of price crossing threshold
- [ ] All API keys loaded from env, never hardcoded
- [ ] P&L recorded atomically to context `positions.*`
- [ ] Latency < 5s per execution (Jupiter quote + execute)