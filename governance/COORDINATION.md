# Lane 4 Coordination Protocol — KuCoin Trading Lane

**Status:** Operational coordination rules for autonomous trading ensemble
**Last Updated:** 2026-05-16
**Version:** 1.0.0
**Companion to:** `governance/ROLES.md`, `governance/SAFETY.md`

---

## Purpose

This document defines **which agent acts when**, **what triggers handoffs**, and **how the trading ensemble maintains coherence** across trading cycles.

---

## Core Coordination Rules

### Rule 1: Orchestrator Decides Direction, Within Risk Limits

**When:** Market data received (tick or cycle timer)
**Why:** Orchestrator has full market context; RiskManager has veto
**Exception:** RiskManager HALT overrides Orchestrator unconditionally

```
Market tick arrives
↓
Orchestrator: [Analyzes regime, signals, confidence]
↓
Orchestrator: "LONG BTC-USDT, confidence=0.72, size=0.01"
↓
RiskManager: [Validates against daily cap, drawdown, circuit breaker]
↓
RiskManager: "APPROVED, size=0.008 (Kelly-adjusted), SL=64200, TP=65800"
```

---

### Rule 2: RiskManager Has Veto, No Override

**When:** Orchestrator requests risk clearance
**Why:** Trading safety supersedes profit opportunity
**Exception:** NEVER — RiskManager veto is absolute within the system

```
✅ GOOD:
Orchestrator: "LONG BTC, size=0.05"
RiskManager: "REJECTED — daily loss cap at 85%, reducing size to 0.008"
Executor: [Places order with reduced size]

❌ BAD:
Orchestrator: "LONG BTC, size=0.05"
RiskManager: "REJECTED"
Executor: "I'll place it anyway at 0.05" ← NEVER HAPPENS
```

---

### Rule 3: Executor Implements, Never Deviates

**When:** RiskManager provides clearance with parameters
**Why:** Separation of decision (Orchestrator + RiskManager) from execution
**Exception:** Executor can reject if exchange conditions violate pre-trade checks

```
RiskManager: "APPROVED, SL=64200, TP=65800, size=0.008"
Executor: [Places order with exact parameters]
Executor: [Reports fill: "FILLED at 64350, SL=64200, TP=65800"]
```

**Executor rejection conditions:**
- Notional below exchange minimum (e.g., KuCoin $1 minimum)
- Exchange API returns margin insufficient
- Symbol temporarily suspended

---

### Rule 4: Auditor Verifies Every Cycle

**When:** Trading cycle completes (after execution or FLAT decision)
**Why:** No cycle closes without verification
**Exception:** NEVER — audit is mandatory, but failure does not halt next cycle

```
Cycle complete
↓
Auditor: [Verifies position state matches expected state]
Auditor: [Verifies risk limits still intact]
Auditor: [Verifies no orphaned orders]
Auditor: "✅ Cycle 42: PASS — positions match, risk OK, no orphans"
```

**On audit failure:**
- Log violation with full context
- Alert via Telegram
- Flag for human review
- Continue next cycle (trading not halted unless RiskManager triggers)

---

### Rule 5: Human Has Constitutional Authority

**When:** Circuit breaker HALT or persistent failure
**Why:** Financial risk ultimately requires human oversight
**Exception:** NEVER — human authority over live trading is absolute

```
RiskManager: "CIRCUIT BREAKER TRIPPED — daily loss cap reached"
↓
System: [Stops all trading]
↓
System: [Saves checkpoint]
↓
System: [Alerts human via Telegram + lane-relay]
↓
Human: [Reviews state, decides: resume / reduce / withdraw]
```

---

## Handoff Triggers

### New Market Cycle

```
Trigger: Cycle timer (default: 60s) or significant price movement
Flow:
Market Data → Intelligence Agents (analyze)
→ Orchestrator (decide)
→ RiskManager (clear)
→ Executor (execute)
→ Monitor (log)
→ Auditor (verify)
→ CheckpointManager (persist)
→ [Next cycle]
```

### Risk Rejection

```
Trigger: RiskManager rejects trade decision
Flow:
Orchestrator → RiskManager → [REJECTED]
→ Orchestrator (reassess as FLAT or reduced)
→ RiskManager (re-clear with new parameters)
→ Executor (execute if approved)
OR
→ [FLAT — no trade this cycle]
→ Auditor (log rejection)
```

### Circuit Breaker Trip

```
Trigger: Daily loss cap reached or portfolio drawdown exceeded
Flow:
RiskManager → [CIRCUIT_BREAKER HALT]
→ Executor (cancel all open orders)
→ Monitor (log HALT event)
→ Auditor (verify clean shutdown)
→ CheckpointManager (save emergency checkpoint)
→ Human (alerted via Telegram + lane-relay)
→ [System idle — awaiting human reset]
```

### Checkpoint Recovery

```
Trigger: Process crash or restart
Flow:
[Crash detected]
→ DeterministicStartup (CLEANUP → INIT → VERIFY)
→ CheckpointManager (load last valid checkpoint)
→ RiskManager (verify circuit breaker state)
→ Orchestrator (restore regime context)
→ [Resume trading if risk OK]
OR
→ [HALT if risk state unknown]
```

---

## Coordination States

The trading ensemble exists in one of these states at any time:

### COLD_START
**Definition:** Process just launched, three-stage startup in progress
**Agents:**
- DeterministicStartup: Active (CLEANUP → INIT → VERIFY)
- All others: Waiting

**Transitions:**
- Startup success → IDLE
- Startup failure → HALTED

---

### IDLE
**Definition:** No active cycle, waiting for market tick or timer
**Agents:**
- Orchestrator: Monitoring regime
- Executor: No open orders (or managing existing positions)
- RiskManager: Monitoring portfolio state
- Auditor: All cycles verified

**Transitions:**
- Cycle timer fires → ANALYZING
- Exchange event (fill, rejection) → EXECUTING

---

### ANALYZING
**Definition:** Intelligence agents processing market data
**Agents:**
- Orchestrator: Active, aggregating signals
- Intelligence agents: Active (RegimeDetector, LeadLag, WhaleWatch)
- Executor: Waiting
- RiskManager: Waiting

**Transitions:**
- Actionable signal → RISK_CLEARING
- No signal (confidence below threshold) → FLAT → AUDITING
- Regime is CRISIS → FLAT → AUDITING

---

### RISK_CLEARING
**Definition:** RiskManager evaluating trade decision
**Agents:**
- Orchestrator: Waiting for clearance
- RiskManager: Active, computing position size and limits
- Executor: Waiting

**Transitions:**
- Approved → EXECUTING
- Rejected (reducible) → back to Orchestrator for size reduction
- Rejected (hard veto) → FLAT → AUDITING
- Circuit breaker trip → HALTING

---

### EXECUTING
**Definition:** Executor placing or managing orders
**Agents:**
- Orchestrator: Monitoring
- RiskManager: Monitoring (position state changed)
- Executor: Active, interacting with exchange

**Transitions:**
- Order filled → MONITORING
- Order rejected → RISK_CLEARING (reassess)
- Exchange failure → RECOVERING

---

### MONITORING
**Definition:** Monitoring open position, checking stop-loss/take-profit
**Agents:**
- All agents: Active monitoring
- Executor: Managing trailing stops, checking fills

**Transitions:**
- Position closed (SL/TP hit) → AUDITING
- New cycle timer → ANALYZING (with open position context)

---

### AUDITING
**Definition:** Auditor verifying cycle consistency
**Agents:**
- Auditor: Active, checking position/risk/log consistency
- All others: Waiting

**Transitions:**
- Audit pass → CHECKPOINTING
- Audit fail → FLAGGED (continue but alert)

---

### CHECKPOINTING
**Definition:** CheckpointManager persisting cycle state
**Agents:**
- CheckpointManager: Active, writing state
- All others: Waiting

**Transitions:**
- Checkpoint saved → IDLE (next cycle)
- Checkpoint failed → RECOVERING

---

### HALTING
**Definition:** Circuit breaker tripped, trading stopped
**Agents:**
- All agents: Stopped
- Executor: Cancels all open orders
- Monitor: Sends alerts

**Transitions:**
- Human reset → IDLE (after verification)
- No human response → remains HALTED

---

### RECOVERING
**Definition:** Recovering from failure (crash, exchange error, checkpoint corruption)
**Agents:**
- DeterministicStartup: Active if full restart
- CheckpointManager: Loading last valid state
- RiskManager: Verifying risk state

**Transitions:**
- Recovery success → IDLE
- Recovery failure → HALTING (alert human)

---

## Loop Prevention

### Infinite Trading Loop Detection

**Problem:** Bot opens and closes the same position repeatedly (whipsaw)

**Detection:**
```python
if cycle_count_1h > 60:
    state = HALTING
    alert("Excessive cycle rate — possible whipsaw. Halting.")
```

**Prevention:**
- Orchestrator confidence threshold prevents low-signal trades
- Minimum time between position reversals (5 minutes)
- Regime CRISIS forces FLAT

---

### Stale State Detection

**Problem:** Agent state diverges from exchange reality

**Detection:**
```python
if executor.position_state != exchange.actual_positions:
    state = RECOVERING
    auditor.log("Position state drift detected")
```

**Prevention:**
- Auditor reconciles position state every cycle
- Executor verifies fills against exchange before updating state
- CheckpointManager validates on save

---

## Conflict Resolution

### RiskManager vs Orchestrator

**Scenario:** Orchestrator wants to trade, RiskManager rejects

```
Resolution: RiskManager wins. Always.
If Orchestrator disagrees, it can:
1. Reduce position size and re-request clearance
2. Accept FLAT for this cycle
3. Never override RiskManager veto
```

---

### Executor vs Exchange

**Scenario:** Exchange rejects order or returns unexpected state

```
Resolution: Executor reports to Orchestrator with exchange error
1. Notional too low → Orchestrator increases size (if risk allows)
2. Margin insufficient → FLAT for this cycle
3. API error → RECOVERING, retry with backoff
4. Rate limited → backoff, retry next cycle
```

---

### Auditor vs Any Agent

**Scenario:** Auditor detects inconsistency

```
Resolution: Auditor logs and alerts
1. Minor inconsistency (e.g., timing drift) → log, continue
2. Position mismatch → flag for RiskManager, halt new trades
3. Checkpoint corruption → RECOVERING
4. Missing fill → Executor re-checks exchange
```

---

## Coordination Metrics

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| **Cycle Time** | 30-120s per cycle | >300s (stuck) or <10s (whipsaw) |
| **Risk Clearance Latency** | <1s | >5s |
| **Execution Latency** | <2s | >10s |
| **Audit Latency** | <1s | >5s |
| **Recovery Time** | <60s | >300s |
| **Cycles Between Halts** | >1000 | <100 |

---

## Emergency Protocols

### Ensemble Halt
**Trigger:** Circuit breaker trip or critical failure
**Action:**
1. Cancel all open orders
2. Save emergency checkpoint
3. Alert human (Telegram + lane-relay)
4. No new trades until human resets

### Rollback
**Trigger:** Checkpoint recovery needed
**Action:**
1. Load last valid checkpoint
2. Verify risk state from checkpoint
3. Reconcile with exchange (actual positions vs checkpoint)
4. Resume if consistent, HALT if not

### Manual Override
**Trigger:** Human sends override via Telegram or lane-relay
**Action:**
1. Execute human instruction (close position, change mode, halt)
2. Log override with full context
3. Save checkpoint after override
4. Return to normal coordination

---

## Extending the Protocol

To add a new agent to the coordination protocol:

1. **Define role** in `governance/ROLES.md`
2. **Add to state machine** — which coordination states include new agent?
3. **Define handoffs** — what artifacts does new agent produce/consume?
4. **Define risk interaction** — how does RiskManager evaluate new agent's actions?
5. **Define fallback** — what happens if new agent fails?
6. **Wire into Orchestrator** — register in agent registry
7. **Test in dry-run** — validate with EXECUTION_MODE=dry_run

---

**Derived from:** `Deliberate-AI-Ensemble/agents/COORDINATION.md` v1.0.0
**Adapted for:** Autonomous margin trading lane context
