---
name: dex-scanner
description: DEX Intelligence Scanner — Phantom, PumpFun, Birdeye, DexScreener, Polymarket
version: 1.0.0
---

# @dex-scanner — DEX Intelligence Scanner

**Domain**: Token launch discovery across Phantom, PumpFun, Birdeye, DexScreener, Polymarket  
**Primary Output**: Normalized token signals with metadata (mint, bonding curve, creator, market cap, liquidity)  
**Context Keys Written**: `scan_results.*`, `health.api_latency.*`, `health.anomalies`

---

## Invocation

```bash
# Scan specific source
@dex-scanner scan --source phantom
@dex-scanner scan --source pumpfun
@dex-scanner scan --source birdeye
@dex-scanner scan --source dexscreener
@dex-scanner scan --source polymarket

# Scan all sources
@dex-scanner scan --all

# Check last results
@dex-scanner status
```

---

## Skills Loaded

| Skill | Purpose |
|-------|---------|
| `identify-assumptions-new` | Map assumptions about new token sources before scanning |
| `brainstorm-experiments-new` | Design lean experiments to validate new DEX sources |
| `prioritize-assumptions` | Focus on highest-risk assumptions (e.g., Phantom parser reliability) |
| `competitor-analysis` | Compare DEX source coverage, latency, reliability |
| `test-driven-development` | Red-Green-Refactor for parser implementations |
| `debugging-and-error-recovery` | Five-step triage for scanner failures |
| `source-driven-development` | Ground API calls in official Phantom/PumpFun/Birdeye docs |

---

## Input/Output Schema

### Input (via CLI args)
```json
{
  "action": "scan|status",
  "source": "phantom|pumpfun|birdeye|dexscreener|polymarket|all",
  "limit": 50,
  "min_market_cap": 0,
  "min_liquidity": 0
}
```

### Output (written to context)
```json
{
  "success": true,
  "scan_time": "2026-06-10T15:30:00Z",
  "source": "phantom",
  "tokens_found": 12,
  "tokens": [
    {
      "mint": "BAumfRj8W5XVrERUAKBAPLBcUC3ZEbFNwkasXDpbpump",
      "name": "3BOSS MEME",
      "symbol": "SOLANA",
      "market_cap_usd": 3686.87,
      "liquidity_usd": 0,
      "bonding_curve": "8LmiQjJQVfHDCMzmTZ3n4ddg2wfCvspsWvpRhXGQTjTk",
      "creator": "unknown",
      "created_at": "2026-06-10T19:11:25Z",
      "dev_holding": 0.88,
      "snipers_holding": 0,
      "source": "phantom"
    }
  ],
  "errors": []
}
```

---

## Implementation Notes

1. **Phantom Parser**: Uses fixed escaped-quote regex (`\\\"initialData\\\":\\{`) from `src/data/dex_intelligence/phantom.py`
2. **Error Handling**: All HTTP calls wrapped with `debugging-and-error-recovery` five-step triage
3. **Latency Tracking**: Records API latency per source to `health.api_latency`
4. **Anomaly Detection**: Flags sources returning 0 tokens for 3+ consecutive cycles

---

## Acceptance Criteria

- [ ] Scans all 5 sources without unhandled exceptions
- [ ] Phantom parser extracts `NEW` array from escaped JSON correctly
- [ ] Results normalized to common schema with mint, name, symbol, market_cap, liquidity
- [ ] Scan latency < 30s per source
- [ ] Errors recorded to context `health.anomalies` with source attribution
- [ ] Context updated atomically via `context.py` locking