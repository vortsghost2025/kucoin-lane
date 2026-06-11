---
name: orchestrator
description: Pipeline Orchestrator — Continuous cycles, state management, signal coordination
version: 1.0.0
---

# @orchestrator — Pipeline Orchestrator

**Domain**: Continuous pipeline cycles, state management, signal log, cross-agent coordination  
**Primary Output**: Cycle results, updated signal log, ledger statistics, next cycle scheduling  
**Context Keys Read**: `pipeline.*`, `positions.*`, `scan_results.*`, `creator_registry.*`, `circuit_breakers.*`, `market_regime.*`  
**Context Keys Written**: `pipeline.*`, `cycle`, `metadata.started_at`

---

## Invocation

```bash
# Run single cycle
@orchestrator run-cycle --interval 15

# Run continuous (daemon)
@orchestrator run-continuous --interval 15 --max-cycles 0

# Get pipeline status
@orchestrator status

# Get signal log summary
@orchestrator signal-log --cycles 10

# Pause/resume
@orchestrator pause
@orchestrator resume
```

---

## Skills Loaded

| Skill | Purpose |
|-------|---------|
| `ci-cd-and-automation` | Quality gate pipelines, feature flags, failure feedback loops |
| `pm-skills/pm-execution:sprint-plan` | Cycle capacity estimation, story selection, risk identification |
| `pm-skills/pm-execution:outcome-roadmap` | Transform feature list into outcome-focused cycle goals |
| `git-workflow-and-versioning` | Trunk-based, atomic commits, change sizing (~100 lines) |
| `pm-skills/pm-toolkit:summarize-meeting` | Cycle summaries for signal log |

---

## Cycle Flow

```
1. PRE-CYCLE
   ├─ Read context, increment cycle counter
   ├─ Check circuit breakers (abort if global/portfolio tripped)
   ├─ Verify API keys present
   └─ Set pipeline.status = "running"

2. SCAN PHASE (parallel)
   ├─ @dex-scanner scan --all
   └─ Wait for all sources (timeout 60s)

3. CREATOR RESOLUTION
   ├─ Extract unique mints from scan_results
   ├─ @creator-intel bulk --mints [list]
   └─ Wait for resolution (timeout 30s)

4. RISK ASSESSMENT
   ├─ For each candidate token: @risk-mgr check
   ├─ Filter to ALLOW verdicts only
   └─ Sort by signal score (creator boost × market cap × liquidity)

5. EXECUTION
   ├─ For top N tokens: @trader execute
   └─ Record results to positions

5. MONITORING
   ├─ @trader monitor (SL/TP check)
   ├─ @monitor health (anomaly detection)
   └─ Update market regime

6. POST-CYCLE
   ├─ Save cycle summary to signal_log.json
   ├─ Update pipeline stats (cycles_completed, win_rate, P&L)
   ├─ Set pipeline.status = "idle"
   └─ Sleep interval_min minutes
```

---

## Signal Log Schema

```json
{
  "cycle": 42,
  "timestamp": "2026-06-10T15:30:00Z",
  "scan": {
    "phantom": 3,
    "pumpfun": 12,
    "birdeye": 8,
    "dexscreener": 15,
    "polymarket": 2
  },
  "creator_resolution": {
    "attempted": 25,
    "resolved": 22,
    "alpha_found": 3
  },
  "risk_filter": {
    "candidates": 40,
    "allowed": 5,
    "reduced": 3,
    "blocked": 32
  },
  "execution": {
    "trades_executed": 3,
    "venues": {"jupiter": 3},
    "total_sol": 0.12
  },
  "monitoring": {
    "sl_tp_triggers": 1,
    "anomalies": 0,
    "market_regime": "trending"
  },
  "ledger": {
    "total_pnl_usd": 47.23,
    "win_rate": 0.62,
    "open_positions": 8
  }
}
```

---

## Feature Flags (via config.json)

```json
{
  "features": {
    "phantom_scanner": true,
    "pumpfun_scanner": true,
    "kucoin_live": false,
    "sl_tp_monitoring": true,
    "creator_intel": true,
    "anomaly_detection": true
  }
}
```

---

## Acceptance Criteria

- [ ] Cycle completes < 90s (excluding sleep)
- [ ] All sub-agent calls have 30s timeout with graceful degradation
- [ ] Circuit breaker check aborts cycle before scanning if tripped
- [ ] Signal log append-only, persisted to `data/signal_log.json`
- [ ] Pipeline status visible via `@orchestrator status`
- [ ] Graceful shutdown on SIGTERM (completes current cycle)
- [ ] Cycle counter increments atomically via context