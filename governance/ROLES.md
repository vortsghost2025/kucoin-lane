# Lane 4 Agent Roles — KuCoin Trading Lane

**Status:** Operational governance for autonomous margin trading
**Last Updated:** 2026-05-16
**Version:** 1.0.0
**Companion to:** `governance/COORDINATION.md`, `governance/SAFETY.md`

---

## Overview

Lane 4 operates as a **4-role autonomous trading ensemble** where specialized agents collaborate through **artifact-driven handoffs** within a single process. The ensemble executes a continuous market-analysis → risk-assessment → execution → audit cycle.

**Key Principle:** Agents don't "talk." Agents exchange artifacts through shared state and structured logs.

---

## The Four Roles

### 1. The Orchestrator (Brain)

**Agent:** `src/intelligence/orchestrator.py` — IntelligenceOrchestrator
**Primary Capability:** Market regime classification, signal aggregation, trade decision

**Inputs:**
- Regime classification from RegimeDetector
- Lead-lag divergence from LeadLagMonitor
- Whale CVD from WhaleWatch
- Market analysis from MarketAnalysisAgent
- Backtest validation from BacktestingAgent
- Risk clearance from RiskManagementAgent
- Entry timing confirmation from EntryTimingValidator

**Outputs:**
- Trade decision (LONG / SHORT / FLAT)
- Confidence score
- Position sizing signal
- Regime-aware stop-loss/take-profit levels

**Boundaries:**
- ❌ **No exchange access** — cannot place orders
- ❌ **No risk override** — cannot bypass circuit breakers
- ✅ **Has market context** — synthesizes all intelligence signals
- ✅ **Has decision authority** — chooses direction within risk limits

---

### 2. The Executor (Hands)

**Agent:** `src/execution/execution_engine.py` — ExecutionEngine (DryRunExecutor / LiveExecutor)
**Primary Capability:** Order placement, position management, exchange interaction

**Inputs:**
- Trade decisions from Orchestrator
- Risk parameters from RiskManager (stop-loss, take-profit, position size)
- Exchange adapter configuration (KuCoin API credentials via env vars)

**Outputs:**
- Order confirmations (filled, partial, rejected)
- Position state updates
- Heartbeat signals
- Telegram notifications

**Boundaries:**
- ❌ **No market analysis** — follows Orchestrator decisions
- ❌ **No risk decisions** — enforces RiskManager limits, never overrides
- ✅ **Has exchange access** — places and manages orders
- ✅ **Can reject** — refuses orders that violate pre-trade risk checks

---

### 3. The Risk Manager (Shield)

**Agent:** `src/risk/risk_manager.py` — RiskManagementAgent
**Supporting:** CircuitBreaker, PortfolioCircuitBreaker, KellyPositionSizer
**Primary Capability:** Pre-trade validation, drawdown protection, position sizing

**Inputs:**
- Trade decision from Orchestrator
- Portfolio state (open positions, PnL, drawdown)
- Asset-specific risk configuration
- Circuit breaker state
- Daily loss cap status

**Outputs:**
- Risk clearance (APPROVED / REJECTED / REDUCED)
- Position size (Kelly-adjusted)
- Stop-loss and take-profit levels
- Circuit breaker triggers (HALT signals)

**Boundaries:**
- ❌ **No order placement** — cannot touch the exchange
- ❌ **No market analysis** — does not interpret signals
- ✅ **Has veto power** — can block any trade
- ✅ **Has portfolio authority** — enforces daily loss cap and drawdown limits

---

### 4. The Auditor (Memory + Sensors)

**Agent:** `src/monitoring/auditor.py` — AuditorAgent
**Supporting:** `src/monitoring/monitor_agent.py` — MonitoringAgent
**Primary Capability:** Post-cycle verification, event logging, safety re-validation

**Inputs:**
- Execution results from Executor
- Risk decisions from RiskManager
- Checkpoint state from CheckpointManager
- Orchestrator decisions with confidence scores

**Outputs:**
- Post-cycle safety reports
- JSONL event logs
- Alert generation (Telegram, lane-relay)
- Checkpoint verification

**Boundaries:**
- ❌ **No code changes** — only observes and logs
- ❌ **No risk override** — reports violations, does not enforce
- ✅ **Has full visibility** — reads all agent state
- ✅ **Validates integrity** — confirms cycle consistency

---

## Artifact-Driven Handoffs

Every handoff within the trading cycle is:
- **Atomic** — single, complete unit of state
- **Inspectable** — logged to JSONL with timestamps
- **Reversible** — checkpoint enables full rollback
- **Typed** — structured Python dataclass/dict with known schema

### Standard Trading Cycle

```
Market Data (external)
↓ (price/volume/orderbook)
Intelligence Agents (RegimeDetector, LeadLag, WhaleWatch, MarketAnalyzer)
↓ (signals + regime)
Orchestrator
↓ (trade decision + confidence)
Risk Manager
↓ (APPROVED/REJECTED + position size + stops)
Executor
↓ (order result + fill)
Monitor (event log)
↓ (cycle complete)
Auditor (post-cycle verification)
↓ (safety report)
CheckpointManager (state persistence)
↓ (cycle restart)
[Next market tick]
```

---

## Interoperability Matrix

| From ↓ To → | Orchestrator | Executor | RiskManager | Auditor | External |
|-------------|-------------|----------|-------------|---------|----------|
| **Orchestrator** | N/A | Trade decision | Risk request | Decision log | — |
| **Executor** | Fill report | N/A | Position state | Execution log | Exchange API |
| **RiskManager** | Risk clearance | Risk params | N/A | Risk audit | — |
| **Auditor** | Safety report | Verification | Compliance check | N/A | Archivist relay |
| **External** | Market data | — | — | — | Telegram |

---

## Coordination Protocol

Defined in `governance/COORDINATION.md` (companion document).

**Key Rules:**
1. **Orchestrator decides direction** — within risk limits
2. **RiskManager has veto** — no trade without risk clearance
3. **Executor implements** — no deviation from approved parameters
4. **Auditor verifies** — no "cycle done" without audit pass
5. **Human has constitutional authority** — circuit breaker HALT requires human to reset

---

## Safety Layer

Defined in `governance/SAFETY.md` (companion document).

**Fallback Rules:**
- If Orchestrator uncertain → FLAT (no trade)
- If Executor fails → cancel all open orders, checkpoint
- If RiskManager triggers HALT → stop all trading, alert human
- If Auditor fails → continue trading but flag for manual review

**Escalation Rules:**
- Portfolio drawdown > daily cap → circuit breaker HALT
- Circuit breaker tripped 3x in 24h → escalate to human
- Exchange API failure → dry-run fallback → escalate if persistent
- Checkpoint corruption → rebuild from last valid, alert human

---

## Checkpoint Schema

```json
{
  "checkpoint_id": "kucoin_lane_20260516_001200",
  "timestamp": "2026-05-16T00:12:00Z",
  "lane": "kucoin-lane",
  "ensemble_state": {
    "orchestrator": {
      "last_regime": "RANGING",
      "last_decision": "FLAT",
      "confidence": 0.45,
      "pending_signals": []
    },
    "executor": {
      "mode": "dry_run",
      "open_positions": [],
      "last_fill": null
    },
    "risk_manager": {
      "circuit_breaker_active": false,
      "portfolio_circuit_breaker_active": false,
      "daily_pnl": 0.0,
      "daily_loss_cap_remaining": 1.0
    },
    "auditor": {
      "last_cycle_pass": true,
      "total_cycles": 0,
      "total_violations": 0
    }
  },
  "constitutional_status": "aligned",
  "mission": "Margin trading within risk parameters"
}
```

---

## Adding New Agents

To extend Lane 4 with a new agent:

1. **Define role and boundaries** — add section above
2. **Define artifact schema** — input/output dataclass
3. **Add to coordination protocol** — update COORDINATION.md
4. **Add to safety protocol** — define fallback/escalation for new agent
5. **Wire into Orchestrator** — register in agent registry
6. **Update __init__.py** — add to package exports
7. **Test in dry-run** — validate with EXECUTION_MODE=dry_run

---

## Metrics and Monitoring

| Metric | Measurement | Healthy Range | Alert Threshold |
|--------|-------------|---------------|-----------------|
| **Decision Latency** | Time from market tick to trade decision | <5s | >30s |
| **Risk Clearance Rate** | Approved / Total decisions | >60% | <30% |
| **Fill Rate** | Filled / Submitted orders | >90% | <70% |
| **Circuit Breaker Trips** | Trips / 24h | 0 | >2 |
| **Audit Pass Rate** | Cycles passing audit / Total cycles | 100% | <95% |
| **Checkpoint Integrity** | Valid loads / Total loads | 100% | <100% |

---

## Theoretical Foundation

This operational structure maps to the universal governance laws:

| Operational Role | Governance Law | Conservation |
|-----------------|---------------|-------------|
| **Orchestrator** | LAW 4: Agent evaluates, doesn't decide for WE | Signal integrity conservation |
| **Executor** | LAW 3: Correction mandatory | Execution fidelity conservation |
| **RiskManager** | LAW 5: Evidence before assertion | Safety conservation |
| **Auditor** | LAW 7: Observable decision trail | Temporal identity conservation |

---

**Derived from:** `Deliberate-AI-Ensemble/agents/ROLES.md` v1.0.0
**Adapted for:** Autonomous margin trading lane context
