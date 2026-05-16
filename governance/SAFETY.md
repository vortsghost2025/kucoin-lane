# Lane 4 Safety Protocol — KuCoin Trading Lane

**Status:** Safety, fallback, and escalation rules for autonomous trading
**Last Updated:** 2026-05-16
**Version:** 1.0.0
**Companion to:** `governance/ROLES.md`, `governance/COORDINATION.md`

---

## Purpose

This document defines **fallback rules**, **escalation paths**, **integrity checks**, and **financial safety enforcement** to ensure the trading lane operates safely under all conditions.

---

## Core Safety Principles

### 1. Capital Preservation Supremacy

**Capital preservation overrides all profit-seeking.**

No agent may:
- Exceed daily loss cap
- Bypass circuit breaker
- Open position without risk clearance
- Override RiskManager veto
- Trade in CRISIS regime

**Enforcement:** RiskManager blocks every trade that violates these rules. The block is unconditional.

---

### 2. Fail-Safe Defaults

**When uncertain, go FLAT rather than trade.**

```python
if confidence < CONFIDENCE_THRESHOLD:
    decision = "FLAT"
if regime == MarketRegime.CRISIS:
    decision = "FLAT"
if risk_clearance == "UNCERTAIN":
    decision = "FLAT"
```

**Rationale:** A missed opportunity costs nothing; a bad trade costs capital.

---

### 3. Reversibility Requirement

**Every trading action must be reversible or containable.**

- All positions have stop-loss (maximum loss bounded)
- All positions have take-profit (exit strategy defined)
- Circuit breaker halts trading on drawdown (loss contained)
- Checkpoints enable full state recovery (restart from known-good state)

**Exception:** Exchange downtime may prevent stop-loss execution. Mitigate with conservative position sizing and never risking more than daily loss cap on a single position.

---

### 4. Transparency Mandate

**All agent actions must be logged and inspectable.**

- Every trade decision logged with reasoning
- Every risk clearance logged with parameters
- Every execution logged with exchange response
- Every cycle audit logged with pass/fail
- Every circuit breaker trip logged with trigger condition

**Enforcement:** MonitoringAgent writes JSONL event log. AuditorAgent verifies log completeness.

---

## Fallback Rules

### Orchestrator Failures

| Failure Type | Symptom | Fallback Action |
|-------------|---------|----------------|
| **Low confidence** | Confidence below threshold | FLAT — no trade |
| **Conflicting signals** | Intelligence agents disagree | FLAT — wait for convergence |
| **Regime CRISIS** | ADX+ATR indicates crisis | FLAT — preserve capital |
| **Context loss** | Cannot determine current regime | FLAT — await next cycle |

**Fallback hierarchy:**
1. FLAT (default safe action)
2. Reduce position size
3. Widen stop-loss (only if RiskManager approves)

---

### Executor Failures

| Failure Type | Symptom | Fallback Action |
|-------------|---------|----------------|
| **Order rejected** | Exchange rejects order | Report to Orchestrator, retry with adjusted params |
| **Notional too low** | Order below exchange minimum | Increase size (if risk allows) or skip |
| **API timeout** | No response from exchange | Retry with exponential backoff (max 3) |
| **Rate limited** | 429 from exchange | Backoff, defer to next cycle |
| **Margin insufficient** | Not enough margin | FLAT — alert human |

**Fallback hierarchy:**
1. Retry with backoff (transient errors)
2. Skip this cycle (persistent errors)
3. Switch to dry-run mode (exchange down)
4. HALT and alert human (margin/API key issues)

---

### RiskManager Failures

| Failure Type | Symptom | Fallback Action |
|-------------|---------|----------------|
| **State unknown** | Cannot determine daily PnL | HALT — no trading without risk visibility |
| **Circuit breaker tripped** | Daily loss cap reached | HALT — cancel orders, alert human |
| **Portfolio circuit breaker** | Portfolio drawdown exceeded | HALT — no new positions |
| **Risk computation error** | Cannot compute position size | FLAT — minimum size only if human approves |

**Fallback hierarchy:**
1. Use last known risk state (if <60s old)
2. HALT all trading (if state stale or unknown)
3. Alert human for manual risk assessment

---

### Auditor Failures

| Failure Type | Symptom | Fallback Action |
|-------------|---------|----------------|
| **Log write failure** | Cannot write JSONL | Continue trading, flag for manual log review |
| **Position mismatch** | State != exchange reality | Flag to RiskManager, halt new trades |
| **Checkpoint corruption** | Cannot save/load checkpoint | Use previous checkpoint, alert human |
| **Integrity violation** | Audit cycle fails | Log violation, continue but alert human |

**Fallback hierarchy:**
1. Log the failure and continue (monitoring non-critical)
2. Halt new trades if position state uncertain
3. Full HALT if integrity violated

---

## Escalation Paths

### Level 1: Agent Self-Resolution
**Trigger:** Minor, recoverable error (e.g., API timeout, rate limit)
**Action:** Agent retries with backoff or defers to next cycle
**Example:** Executor retries order placement after 429 response

**Criteria for escalation:** 3 failed self-resolution attempts

---

### Level 2: Orchestrator Reassessment
**Trigger:** Agent cannot self-resolve, but trading can continue
**Action:** Orchestrator adjusts strategy (FLAT, reduce size, change direction)
**Example:** Executor reports persistent notional rejection → Orchestrator increases size

**Criteria for escalation:** RiskManager triggers circuit breaker

---

### Level 3: Human Alert
**Trigger:** Circuit breaker tripped or persistent failure
**Action:** Alert human via Telegram + lane-relay to Archivist
**Example:** "Portfolio circuit breaker tripped — drawdown 8.2% exceeds 5% limit. Trading halted."

**Resolution:** Human reviews state, decides action

---

### Level 4: Emergency Halt
**Trigger:** Critical failure (exchange down, API key invalid, checkpoint corruption)
**Action:** Halt all operations, cancel orders, save emergency checkpoint, alert human
**Example:** "Exchange API returning 401 — API key may be invalid. All trading halted."

**Resolution:** Requires human intervention (check API keys, verify exchange status)

---

## Financial Safety Enforcement

### Pre-Trade Validation (RiskManager)

Every trade must pass ALL checks before execution:

```python
def validate_trade(decision, portfolio_state):
    checks = [
        check_daily_loss_cap(decision, portfolio_state),
        check_portfolio_drawdown(decision, portfolio_state),
        check_position_size(decision, portfolio_state),
        check_circuit_breaker_state(),
        check_notional_minimum(decision),
        check_regime_safety(decision),
        check_session_limits(decision, portfolio_state),
    ]

    failures = [c for c in checks if not c.passed]

    if any(c.critical for c in failures):
        return TradeValidation(REJECTED, failures, action="HALT")

    if failures:
        return TradeValidation(REDUCED, failures, action="reduce_size")

    return TradeValidation(APPROVED, [], action="execute")
```

---

### Circuit Breaker Rules

**PnL Circuit Breaker** (`risk/circuit_breaker.py`):
- Tracks rolling PnL over configurable window
- Trips when cumulative loss exceeds threshold
- Auto-resets after timeout OR manual reset

**Portfolio Circuit Breaker** (`risk/portfolio_circuit_breaker.py`):
- Tracks portfolio-level drawdown from peak
- Daily loss cap enforcement
- Persistent state across restarts (writes to file)
- Requires manual reset after trip

**Kelly Criterion** (`risk/kelly_criterion.py`):
- Position sizing capped at 0.25x Kelly (quarter-Kelly)
- Win rate and payoff ratio tracked per asset
- Reduces size in low-confidence regimes

---

### Position Size Limits

| Asset Class | Max Position (Notional) | Max Daily Loss | Max Drawdown |
|-------------|------------------------|----------------|--------------|
| **BTC** | 2% of portfolio | 1% of portfolio | 5% from peak |
| **ETH** | 2% of portfolio | 1% of portfolio | 5% from peak |
| **Alt (top-20)** | 1% of portfolio | 0.5% of portfolio | 3% from peak |
| **Other** | 0.5% of portfolio | 0.25% of portfolio | 2% from peak |

**Override:** Only human can increase these limits.

---

## Integrity Verification

### Checkpoint Integrity

Every checkpoint includes a state hash:

```python
checkpoint = {
    "checkpoint_id": "kucoin_lane_20260516_001200",
    "lane": "kucoin-lane",
    "ensemble_state": { ... },
    "state_hash": compute_hash(ensemble_state),
    "previous_checkpoint": "kucoin_lane_20260516_001100",
    "chain_valid": True
}

def load_checkpoint(path):
    cp = read_json(path)
    if compute_hash(cp["ensemble_state"]) != cp["state_hash"]:
        raise CheckpointIntegrityError("Hash mismatch — checkpoint corrupted")
    return cp
```

---

### Execution Integrity

Every executed order is verified against exchange response:

```python
def verify_fill(submitted_order, exchange_response):
    if submitted_order.side != exchange_response.side:
        alert("Side mismatch — submitted {submitted_order.side}, got {exchange_response.side}")
    if abs(submitted_order.size - exchange_response.size) > SIZE_TOLERANCE:
        alert("Size mismatch — submitted {submitted_order.size}, got {exchange_response.size}")
    log_verification(submitted_order, exchange_response)
```

---

### Cycle Integrity

Auditor verifies at end of each cycle:

1. Position state matches exchange reality
2. Risk limits still intact (no silent bypass)
3. No orphaned orders (submitted but never confirmed)
4. Event log complete (no missing entries)
5. Checkpoint saved successfully

---

## Emergency Procedures

### Code Red: Circuit Breaker Trip

**Trigger:** Daily loss cap reached or portfolio drawdown exceeded

**Actions:**
1. **HALT** — Stop all new trade decisions
2. **CANCEL** — Cancel all open orders on exchange
3. **SAVE** — Emergency checkpoint with HALT flag
4. **ALERT** — Telegram notification + lane-relay to Archivist
5. **AUDIT** — Log full portfolio state at HALT time
6. **AWAIT** — No resumption until human resets

**Resolution:**
- Human reviews portfolio state
- Human resets circuit breaker (manual action)
- New checkpoint established post-reset
- Trading resumes from IDLE state

---

### Code Yellow: Exchange Degradation

**Trigger:** Exchange API errors, high latency, or partial outages

**Actions:**
1. **PAUSE** — No new trade decisions
2. **VERIFY** — Check existing positions and open orders
3. **WIDEN** — Move stop-losses to conservative levels (if exchange responsive)
4. **ALERT** — Notify human of degraded conditions
5. **SWITCH** — If persistent, switch to dry-run mode
6. **AWAIT** — Resume live when exchange stable

---

### Code Blue: Agent Unavailability

**Trigger:** Required agent crashes or becomes non-responsive

**Actions:**
1. **DETECT** — Heartbeat timeout or exception
2. **FALLBACK** —
   - Orchestrator down → FLAT for all cycles until recovery
   - Executor down → Cannot trade → HALT
   - RiskManager down → Cannot clear risk → HALT
   - Auditor down → Continue trading, flag for manual audit
3. **RECOVER** — Restart from last checkpoint
4. **VERIFY** — Auditor runs full reconciliation post-recovery

---

## Recovery Procedures

### Standard Recovery (Agent Crash)

```
1. Process restart (systemd or docker restart)
2. DeterministicStartup: CLEANUP → INIT → VERIFY
3. CheckpointManager loads last valid checkpoint
4. RiskManager verifies circuit breaker state
5. Executor reconciles positions with exchange
6. Auditor runs full verification
7. Resume from IDLE if all checks pass
```

---

### Deep Recovery (Checkpoint Corrupted)

```
1. Detect corruption (hash mismatch)
2. Search for previous valid checkpoint
3. Load valid checkpoint (may lose recent state)
4. Executor reconciles with exchange (source of truth for positions)
5. RiskManager re-evaluates from exchange state
6. New checkpoint established
7. Resume with explicit acknowledgment of state gap
```

---

### Emergency Recovery (Total State Loss)

```
1. No valid checkpoints available
2. DeterministicStartup runs full initialization
3. Executor queries exchange for all open positions
4. RiskManager computes state from exchange data
5. Orchestrator enters FLAT until next cycle
6. New checkpoint created from exchange state
7. Human alerted to verify state before resuming
```

---

## Safety Metrics

| Metric | Measurement | Safe Range | Alert Threshold |
|--------|-------------|-----------|-----------------|
| **Circuit Breaker Trips** | Trips / 24h | 0 | >2 |
| **Daily Loss Utilization** | Current daily loss / Cap | <50% | >80% |
| **Drawdown from Peak** | Portfolio drawdown % | <2% | >4% |
| **Audit Failure Rate** | Failed audits / Total cycles | 0% | >5% |
| **Checkpoint Integrity** | Valid loads / Total loads | 100% | <100% |
| **Exchange Error Rate** | API errors / Total requests | <1% | >5% |

---

## Updating Safety Rules

To add new safety rule:

1. **Define trigger** — What market or portfolio condition activates this rule?
2. **Define response** — What action should the ensemble take? (FLAT, HALT, REDUCE)
3. **Implement in RiskManager** — Add check to `validate_trade()`
4. **Add to escalation matrix** — Define who decides resolution
5. **Add to audit log** — Ensure rule violations logged to JSONL
6. **Test in dry-run** — Validate with EXECUTION_MODE=dry_run
7. **Document** — Update this file with new rule

---

**Derived from:** `Deliberate-AI-Ensemble/agents/SAFETY.md` v1.0.0
**Adapted for:** Autonomous margin trading lane context
