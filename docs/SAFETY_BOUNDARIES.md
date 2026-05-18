# Safety Boundary Audit — KuCoin Trading Lane

**Status:** Implementation-level safety boundary inventory and gap analysis  
**Last Updated:** 2026-05-17  
**Version:** 1.0.0  
**Companion to:** `governance/SAFETY.md` (policy), this document (implementation reality)  
**Audit Scope:** All code paths that can submit real orders, all gates/flags/checks that prevent accidental live trading, all mutating exchange methods, and all risk/circuit-breaker mechanisms  

---

## Purpose

`governance/SAFETY.md` defines **what should happen** (policy). This document maps **what actually happens** (implementation), including every gap where code behavior diverges from policy. Use this to:

1. Understand every safety boundary in the codebase at the function/line level
2. Identify which boundaries are fail-closed (safe default) vs fail-open (unsafe default)
3. Track gaps between `governance/SAFETY.md` policy and actual code
4. Prioritize fixes by severity

---

## Code Paths That Submit Real Orders

There are exactly **3 code paths** that submit real orders to the exchange. All three are inside `LiveExecutor.execute()`.

| # | Method | File:Line | Order Type | API Call |
|---|--------|-----------|------------|----------|
| OP-1 | `self.adapter.place_order(side="buy")` | `execution_engine.py:646` | Entry order (market or limit) | `kucoin_client.create_market_order()` or `create_limit_order()` |
| OP-2 | `self.adapter.place_stop_loss(side="sell")` | `execution_engine.py:656` | Stop-loss order | `kucoin_client.create_stop_limit_order()` |
| OP-3 | `self.adapter.place_order(side="sell")` | `execution_engine.py:665` | Take-profit order (limit sell) | `kucoin_client.create_limit_order()` |

**No other code path submits real orders.** `DryRunExecutor.execute()` tracks paper positions only. All other adapter methods (`cancel_order`, `borrow`, `repay`) are available but not called by `LiveExecutor.execute()`.

---

## Mutating Exchange Methods

The `ExchangeAdapter` ABC defines 7 mutating methods. Only 3 are used by `LiveExecutor.execute()`.

| # | Method | File:Line | Used by LiveExecutor? | Risk |
|---|--------|-----------|----------------------|------|
| M-1 | `place_order()` | `exchange_adapter.py:36-39` | **YES** (entry + TP) | Opens/closes real positions |
| M-2 | `place_stop_loss()` | `exchange_adapter.py:152` | **YES** (SL) | Creates stop orders |
| M-3 | `cancel_order()` | `exchange_adapter.py:42` | **NO** | Could cancel protective stops |
| M-4 | `borrow()` | `exchange_adapter.py:54` | **NO** | Opens margin debt |
| M-5 | `repay()` | `exchange_adapter.py:57` | **NO** | Closes margin debt |
| M-6 | `get_balance()` | `exchange_adapter.py:119` | YES (read-only) | No mutation risk |
| M-7 | `get_ticker()` | `exchange_adapter.py:161` | YES (read-only) | No mutation risk |

**Gap M-3:** `cancel_order()` is not wired into any safety/emergency flow. `governance/SAFETY.md` Code Red procedure says "Cancel all open orders on exchange" but no code implements this.

**Gap M-4/M-5:** `borrow()` and `repay()` exist but are never called. Margin debt management is unimplemented.

---

## Mode Selection Gates

There are **5 mode-selection paths** that determine whether the bot runs in dry-run or live mode.

### SB-01: PAPER_TRADING env var

| Field | Value |
|-------|-------|
| **File** | `config.py:13` |
| **Code** | `"paper_trading": os.getenv("PAPER_TRADING", "true").lower() == "true"` |
| **Default** | `true` (dry-run) |
| **Fail mode** | **Fail-closed** (defaults to paper) |
| **Guards** | Sets `DRY_RUN` flag at `config.py:95` |

### SB-02: LIVE_TRADING env var

| Field | Value |
|-------|-------|
| **File** | `config.py:96` |
| **Code** | `LIVE_TRADING = os.getenv("LIVE_TRADING", "false").lower() == "true"` |
| **Default** | `false` (no live trading) |
| **Fail mode** | **Fail-closed** (defaults to no live) |
| **Guards** | Read by `ExecutionAgent.__init__()` and `select_executor()` |
| **Gap** | **Not documented in `.env.example`** — users have no template for this variable |

### SB-03: KUCOIN_USE_SANDBOX env var

| Field | Value |
|-------|-------|
| **File** | `exchange_adapter.py:77` |
| **Code** | `use_sandbox = os.getenv("KUCOIN_USE_SANDBOX", "false").lower() == "true"` |
| **Default** | `false` (production API) |
| **Fail mode** | **Fail-OPEN** — defaults to production API endpoint `openapi-v2.kucoin.com` |
| **Guards** | Selects between sandbox and production base URL |
| **Gap** | **Not documented in `.env.example`** — and defaults to the dangerous option |
| **Policy violation** | `governance/SAFETY.md` principle 2 (fail-safe defaults) says "when uncertain, go FLAT" — this should default to sandbox |

### SB-04: ExecutionAgent.__init__() mode fallback

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:755-782` |
| **Behavior** | If both `DRY_RUN=False` and `LIVE_TRADING=False`, falls back to `DryRunExecutor` |
| **Fail mode** | **Fail-closed** (defaults to dry-run) |
| **Conflict** | `select_executor()` raises `RuntimeError` for the same inputs — two codepaths with different failure modes |

### SB-05: select_executor() factory

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:814-832` |
| **Code** | Raises `RuntimeError("Invalid mode: either DRY_RUN must be True or LIVE_TRADING must be True")` if both are False |
| **Fail mode** | **Fail-closed** (crashes rather than proceeding) |
| **Gap** | Does **NOT** pass safety limit parameters to LiveExecutor config (see SB-12 through SB-15) |

### Design inconsistency: Dead EXECUTION_MODE env var

| Field | Value |
|-------|-------|
| **Dockerfile** | Sets `EXECUTION_MODE=paper` (line ~8) |
| **docker-compose.yml** | Sets `EXECUTION_MODE=paper` |
| **Python code** | **Never reads `EXECUTION_MODE`** — this variable is completely dead |
| **Impact** | Misleading — operators may believe changing this var switches modes |

### Design inconsistency: PAPER_TRADING vs DRY_RUN naming

`PAPER_TRADING` (user-facing) maps to `DRY_RUN` (internal). `LIVE_TRADING` is a separate flag. The relationship is:

```
DRY_RUN = PAPER_TRADING  (config.py:95)
LIVE_TRADING = os.getenv("LIVE_TRADING", "false")  (config.py:96)
```

These are **independent flags**, not a single mode enum. Both could theoretically be `True` simultaneously — `select_executor()` would enter live mode in that case.

---

## LiveExecutor Validation Gates

These are the checks that `LiveExecutor.execute()` runs **before** placing a real order.

### SB-06: position_approved / risk_approved check

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:596-605` |
| **Code** | `if position_approved is False or risk_approved is False:` |
| **Default values** | Both default to `None` via `input_data.get("position_approved", None)` |
| **Fail mode** | **CRITICAL FAIL-OPEN** |
| **Explanation** | `is False` is Python identity comparison. `None is False` evaluates to `False`, so if these keys are missing from `input_data`, the trade **proceeds without risk approval** |
| **Policy violation** | `governance/SAFETY.md` principle 1: "No agent may open position without risk clearance" |
| **Fix required** | Change to `if not position_approved or not risk_approved:` to require explicit `True` values |

**This is the most dangerous gap in the system.** Any caller that forgets to include `position_approved=True` and `risk_approved=True` in `input_data` will have their trade executed on the live exchange without any risk clearance.

### SB-07: market_data / position_size validation

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:607-613` |
| **Code** | `if not market_data or position_size <= 0:` |
| **Fail mode** | **Fail-closed** — rejects trades with no market data or non-positive size |

### SB-08: Session limits validation

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:572-577`, `615-622` |
| **Code** | Checks `total_trades >= max_trades_per_session` and `len(open_positions) >= max_open_positions` |
| **Defaults** | `max_open_positions=1`, `max_trades_per_session=2` |
| **Fail mode** | **Fail-closed** — rejects trades when limits reached |

### SB-09: Position value vs account balance check

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:546-548` |
| **Code** | `if position_value > account_balance * 1.1:` |
| **Condition** | Only runs if `account_balance is not None` |
| **Fail mode** | **Fail-OPEN if `account_balance` is `None`** — the check is silently skipped |

### SB-10: Order type validation

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:550-551` |
| **Code** | `if self.order_type not in {"market", "limit"}:` |
| **Default** | `"market"` |
| **Fail mode** | **Fail-closed** — rejects unknown order types |

### SB-11: Max open positions check (in _validate_live_trade)

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:552-553` |
| **Code** | `if len(self.open_positions) >= self.max_open_positions:` |
| **Default** | `1` |
| **Fail mode** | **Fail-closed** |

### SB-12: max_position_size_usd check

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:506` (init), `554-557` (check) |
| **Code** | `self.max_position_size_usd = config.get("max_position_size_usd")` |
| **Default** | `None` |
| **Fail mode** | **FAIL-OPEN** — when `None`, the check `if self.max_position_size_usd is not None` at line 554 is skipped entirely |
| **select_executor gap** | `select_executor()` at line 815-819 never passes this key in the config dict |

### SB-13: max_trade_loss_usd check

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:507` (init), `558-562` (check) |
| **Code** | `self.max_trade_loss_usd = config.get("max_trade_loss_usd")` |
| **Default** | `None` |
| **Fail mode** | **FAIL-OPEN** — when `None`, projected loss check is skipped |
| **select_executor gap** | Not passed by `select_executor()` |

### SB-14: max_daily_loss_usd check

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:508` (init), `563-566` (check) |
| **Code** | `self.max_daily_loss_usd = config.get("max_daily_loss_usd")` |
| **Default** | `None` |
| **Fail mode** | **FAIL-OPEN** — when `None`, daily loss check is skipped |
| **select_executor gap** | Not passed by `select_executor()` |
| **Note** | `RiskManagementAgent` has a separate `MAX_DAILY_LOSS_CAP = 0.02` (2%) but this is not enforced by `LiveExecutor` |

### SB-15: min_balance_usd check

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:509` (init), `567-569` (check) |
| **Code** | `self.min_balance_usd = config.get("min_balance_usd")` |
| **Default** | `None` |
| **Fail mode** | **FAIL-OPEN** — when `None`, minimum balance check is skipped |
| **select_executor gap** | Not passed by `select_executor()` |

---

## Stop-Loss / Take-Profit Failure Handling

### SB-16: Stop-loss placement failure

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:654-662` |
| **Code** | `except Exception as e: self.log("error", f"CRITICAL: Failed to place stop-loss: {e}")` |
| **Behavior** | Logs CRITICAL but **does NOT** unwind the entry order |
| **Fail mode** | **CRITICAL FAIL-OPEN** — position is open on exchange with NO stop-loss |
| **Policy violation** | `governance/SAFETY.md` principle 3: "All positions have stop-loss (maximum loss bounded)" |
| **Fix required** | On SL failure: cancel the entry order, return error, and alert human |

### SB-17: Take-profit placement failure

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:663-671` |
| **Code** | `except Exception as e: self.log("error", f"CRITICAL: Failed to place take-profit: {e}")` |
| **Behavior** | Logs CRITICAL but does NOT unwind the entry order or stop-loss |
| **Fail mode** | **FAIL-OPEN** — position is open with a stop-loss but no take-profit |
| **Impact** | Less critical than SB-16 (SL still protects downside), but position has no automated exit on profit |

### SB-18: Trade recorded as successful despite SL/TP failure

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:690-691`, `704-720` |
| **Code** | `"stop_order_id": None, "tp_order_id": None` — always `None` regardless of SL/TP success |
| **Behavior** | `success: True` and `trade_executed: True` returned even when stop-loss failed |
| **Fail mode** | **FAIL-OPEN** — downstream agents/monitors cannot distinguish fully-protected trades from unprotected trades |

---

## Circuit Breaker Integration

### SB-19: CircuitBreaker class (PnL-based)

| Field | Value |
|-------|-------|
| **File** | `risk/circuit_breaker.py` (98 lines) |
| **Behavior** | Tracks rolling PnL, trips when cumulative loss exceeds threshold (default 8%) over a time window (default 60 min) |
| **Integration** | **NOT INTEGRATED into LiveExecutor** — zero imports from `risk/` in `execution_engine.py` |
| **Only usage** | `IntelligenceOrchestrator` has a `circuit_breaker_active` boolean flag (line 97) but does NOT use the `CircuitBreaker` class |
| **Policy violation** | `governance/SAFETY.md` "Circuit Breaker Rules" section describes this as an active safety mechanism |

### SB-20: PortfolioCircuitBreaker class (drawdown + daily loss)

| Field | Value |
|-------|-------|
| **File** | `risk/portfolio_circuit_breaker.py` (131 lines) |
| **Behavior** | Tracks portfolio drawdown from peak and daily loss, persists state to `portfolio_cb_state.json`, raises `CircuitBreakTriggered` exception |
| **Integration** | **NOT INTEGRATED into LiveExecutor** — zero imports from `risk/` in `execution_engine.py` |
| **State artifact** | `portfolio_cb_state.json` exists at project root (written by something, but not by the execution engine) |
| **Policy violation** | `governance/SAFETY.md` Code Red procedure requires circuit breaker to halt trading |

### SB-21: IntelligenceOrchestrator.circuit_breaker_active flag

| Field | Value |
|-------|-------|
| **File** | `orchestrator.py:97`, `153-158` |
| **Code** | `self.circuit_breaker_active = False` / `activate_circuit_breaker(reason)` |
| **Behavior** | Sets a boolean flag and pauses trading via `self.trading_paused = True` |
| **Gap** | This is a **soft gate** — it only affects the Orchestrator's workflow. `LiveExecutor` never checks `orchestrator.circuit_breaker_active` or `orchestrator.trading_paused` |

### SB-22: IntelligenceOrchestrator.is_trading_allowed()

| Field | Value |
|-------|-------|
| **File** | `orchestrator.py:160+` |
| **Behavior** | Returns `(False, reason)` when `trading_paused=True` or `circuit_breaker_active=True` |
| **Gap** | Only checked within Orchestrator's workflow — `LiveExecutor` has no reference to the Orchestrator and cannot be stopped by this check |

---

## Risk Management Integration

### SB-23: RiskManagementAgent position approval

| Field | Value |
|-------|-------|
| **File** | `risk/risk_manager.py:94-186` |
| **Behavior** | Validates signal strength, win rate, volatility, entry timing, position size, and daily loss cap |
| **Output** | Sets `position_approved` (True/False) and `risk_approved` in output data |
| **Integration gap** | LiveExecutor reads these from `input_data` (SB-06) but the `is False` check means `None` (missing keys) passes through |
| **Trust model** | RiskManager's approval is **advisory, not mandatory** — the executor does not require it |

### SB-24: MAX_DAILY_LOSS_CAP (RiskManager)

| Field | Value |
|-------|-------|
| **File** | `risk_manager.py:15` |
| **Code** | `MAX_DAILY_LOSS_CAP = 0.02` (2% of account) |
| **Behavior** | Hard-coded cap that overrides any higher `max_daily_loss` config value |
| **Integration gap** | Only enforced by `RiskManagementAgent`, NOT by `LiveExecutor`'s own `_validate_live_trade()` |

### SB-25: enforce_min_position_size_only flag

| Field | Value |
|-------|-------|
| **File** | `risk_manager.py:70-72`, `config.py:28-31` |
| **Default** | `True` |
| **Behavior** | When `True`, skips signal strength and win rate validation (`_validate_trade()` is not called) |
| **Impact** | Trades are approved based on minimum position size alone, ignoring signal quality |
| **Fail mode** | **Fail-OPEN** — low-quality signals can pass risk assessment |

### SB-26: KellyCriterion position sizer

| Field | Value |
|-------|-------|
| **File** | `risk/kelly_criterion.py` |
| **Integration** | **NOT wired into execution pipeline** — `LiveExecutor` never imports or uses it |
| **Policy reference** | `governance/SAFETY.md` describes "Kelly Criterion" as an active position sizing mechanism |

---

## Monitoring and Audit

### SB-27: AuditorAgent post-cycle audit

| Field | Value |
|-------|-------|
| **File** | `monitoring/auditor.py:33-92` |
| **Behavior** | Re-validates downtrend detection, risk enforcement, and position sizing after each cycle |
| **Gap** | Violations are **only logged** — no protective action (no circuit breaker activation, no trade halt, no alert escalation) |
| **Policy violation** | `governance/SAFETY.md` says Auditor violations should trigger escalation |

### SB-28: MonitoringAgent alerts

| Field | Value |
|-------|-------|
| **File** | `monitoring/monitor_agent.py` |
| **Behavior** | Generates alerts based on configured thresholds |
| **Gap** | Alerts are informational only — they do not halt trading or activate circuit breakers |

### SB-29: Telegram notifications

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:45-60` |
| **Behavior** | Sends start/stop messages via Telegram |
| **Gap** | Not wired to send alerts on SL/TP failures, circuit breaker trips, or risk violations |

---

## Startup and State Management

### SB-30: DeterministicStartup three-stage verification

| Field | Value |
|-------|-------|
| **File** | `deterministic_startup.py` |
| **Behavior** | CLEANUP -> INIT -> VERIFY stages before trading begins |
| **Integration** | Called at bot startup |

### SB-31: _check_existing_positions_at_startup()

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:218-219` (call), `734-738` (stub) |
| **Code** | `if "Live" in self.__class__.__name__: self._check_existing_positions_at_startup()` |
| **Behavior** | Override exists in `LiveExecutor` (line 734+) but the base class version is a `pass` stub |
| **Gap** | If the base class version is accidentally called (e.g., via super()), existing positions are not reconciled |

### SB-32: Session state and heartbeat

| Field | Value |
|-------|-------|
| **File** | `execution_engine.py:131-169` |
| **Behavior** | Writes `SESSION_STATE.json` and heartbeat files on every status transition |
| **Fail mode** | **Fail-closed for external monitoring** — if writes fail, only a warning is logged, but the bot continues |

---

## Missing Safety Boundaries (Not Implemented)

| # | Boundary | Description | Policy Reference |
|---|----------|-------------|-----------------|
| MS-1 | **Kill switch** | No mechanism to immediately halt all trading and cancel all open orders from outside the process | SAFETY.md Code Red step 2: "Cancel all open orders" |
| MS-2 | **Order rate limiter** | No rate limiting on order placement — a bug could flood the exchange | SAFETY.md doesn't mention this explicitly |
| MS-3 | **Total exposure cap** | No limit on total portfolio exposure across all positions (only per-position limits exist) | SAFETY.md position size limits table |
| MS-4 | **Re-entry cooldown after circuit breaker** | `CircuitBreaker` has auto-reset after cooldown, but `PortfolioCircuitBreaker` requires manual reset — yet neither is integrated into the execution path | SAFETY.md Code Red step 6: "No resumption until human resets" |
| MS-5 | **Two-person rule for live mode** | No confirmation or secondary authorization required to enable live trading | SAFETY.md principle 2 (fail-safe defaults) |
| MS-6 | **Startup safety config dump** | No log output of all active safety limits at startup — operators cannot verify which limits are active (vs defaulted to None) | SAFETY.md principle 4 (transparency) |
| MS-7 | **DryRunExecutor SL/TP simulation** | `DryRunExecutor.execute()` does not simulate stop-loss or take-profit order placement, so the dry-run path cannot catch SL/TP failures that would occur in live mode | SAFETY.md principle 3 (reversibility) |

---

## .env.example Gaps

The following safety-critical environment variables are **missing** from `config/.env.example`:

| Variable | Defined in | Default | Impact of absence |
|----------|-----------|---------|-------------------|
| `LIVE_TRADING` | `config.py:96` | `false` | Operators may not know this flag exists, or may set `PAPER_TRADING=false` expecting live mode (which doesn't work — `LIVE_TRADING` must be explicitly `true`) |
| `KUCOIN_USE_SANDBOX` | `exchange_adapter.py:77` | `false` | Operators cannot discover the sandbox option from the template |
| `MIN_WIN_RATE` | `config.py:25` | `0.45` | Risk validation threshold undocumented |
| `ENFORCE_MIN_POSITION_SIZE_ONLY` | `config.py:28-31` | `false` | Critical flag that bypasses signal/win-rate validation — undocumented |
| `POSITION_SIZE_USD` | `config.py:92` | `5.0` | Live trade size undocumented |
| `MONITOR_INTERVAL_MIN` | `config.py:93` | `5` | Cycle interval undocumented |

---

## select_executor() Config Gap Analysis

`select_executor()` at `execution_engine.py:814-820` builds a config dict with only 4 keys:

```python
config = {
    "dry_run": dry_run,
    "live_trading": live_trading,
    "position_size_usd": float(POSITION_SIZE_USD),
    "monitor_interval_min": int(MONITOR_INTERVAL_MIN),
}
```

**Missing keys that LiveExecutor.__init__() reads:**

| Key | LiveExecutor init line | Default when missing | Effect |
|-----|----------------------|---------------------|--------|
| `max_position_size_usd` | 506 | `None` | No position size cap |
| `max_trade_loss_usd` | 507 | `None` | No per-trade loss cap |
| `max_daily_loss_usd` | 508 | `None` | No daily loss cap |
| `min_balance_usd` | 509 | `None` | No minimum balance check |
| `max_open_positions` | 504 | `1` | Uses safe default |
| `max_trades_per_session` | 505 | `2` | Uses safe default |
| `order_type` | 510 | `"market"` | Uses safe default |

**When `select_executor()` is the entry point, 4 of 6 safety limits are completely disabled.**

---

## Policy vs Implementation Gap Summary

| `governance/SAFETY.md` Policy | Implementation Status | Gap |
|-------------------------------|----------------------|-----|
| "No agent may open position without risk clearance" | `position_approved is False` check (SB-06) allows `None` through | **P0 — trades execute without risk approval** |
| "All positions have stop-loss" | SL failure logs but doesn't unwind entry (SB-16) | **P0 — unprotected positions** |
| "Fail-safe defaults" | `KUCOIN_USE_SANDBOX` defaults to production (SB-03) | **P1 — defaults to dangerous endpoint** |
| "Circuit breaker halts trading on drawdown" | `CircuitBreaker` and `PortfolioCircuitBreaker` never imported by LiveExecutor (SB-19, SB-20) | **P0 — circuit breakers are dead code in execution path** |
| "Kelly Criterion position sizing" | `KellyPositionSizer` not wired into pipeline (SB-26) | **P2 — exists but unused** |
| "Code Red: Cancel all open orders" | `cancel_order()` not called by any emergency flow (M-3) | **P1 — emergency procedure not implemented** |
| "Auditor violations trigger escalation" | Auditor violations only logged (SB-27) | **P1 — no protective action** |
| "Never risk more than 1% of capital per trade" | `RiskManagementAgent` enforces, but `LiveExecutor` doesn't independently verify (SB-23/24) | **P1 — single point of failure** |

---

## Critical Findings Summary

### P0 (Immediate fix required — money at risk)

| ID | Finding | File:Line | Impact |
|----|---------|-----------|--------|
| P0-1 | `position_approved is False` fails on `None` | `execution_engine.py:599` | Trades execute without risk clearance |
| P0-2 | 4 safety limits default to `None` (disabled) | `execution_engine.py:506-509` | No position/daily/balance caps when `select_executor()` used |
| P0-3 | `select_executor()` doesn't pass safety limits | `execution_engine.py:815-819` | All 4 limits above guaranteed disabled via this path |
| P0-4 | Circuit breakers not integrated into LiveExecutor | `execution_engine.py` imports | No automated trading halt on drawdown |
| P0-5 | Stop-loss failure doesn't unwind entry order | `execution_engine.py:654-671` | Unprotected live positions |

### P1 (Fix before next live deployment)

| ID | Finding | File:Line | Impact |
|----|---------|-----------|--------|
| P1-1 | `KUCOIN_USE_SANDBOX` defaults to production | `exchange_adapter.py:77` | Accidental production API use |
| P1-2 | `cancel_order()` not wired into emergency flow | `exchange_adapter.py:42` | Code Red procedure not implementable |
| P1-3 | Auditor violations don't trigger protective action | `monitoring/auditor.py:68-73` | Safety violations logged but ignored |
| P1-4 | Two mode-selection paths with different failure modes | `execution_engine.py:755-782` vs `814-832` | Confusing, one crashes, one defaults to dry-run |
| P1-5 | `EXECUTION_MODE` env var is dead code | `Dockerfile`, `docker-compose.yml` | Operators misled about mode control |
| P1-6 | `.env.example` missing `LIVE_TRADING` and `KUCOIN_USE_SANDBOX` | `config/.env.example` | Critical vars undiscoverable |

### P2 (Fix when convenient — design debt)

| ID | Finding | File:Line | Impact |
|----|---------|-----------|--------|
| P2-1 | `enforce_min_position_size_only=True` skips signal validation | `risk_manager.py:70-72` | Low-quality signals can pass risk |
| P2-2 | `KellyPositionSizer` not wired into pipeline | `risk/kelly_criterion.py` | Policy-described feature not operational |
| P2-3 | `DryRunExecutor` doesn't simulate SL/TP placement | `execution_engine.py:420-485` | Dry-run can't catch live SL/TP failures |
| P2-4 | `stop_order_id` / `tp_order_id` always `None` in trade record | `execution_engine.py:690-691` | No tracking of protective orders |
| P2-5 | `PAPER_TRADING` vs `DRY_RUN` naming confusion | `config.py:13,95` | Cognitive overhead for operators |
| P2-6 | `account_balance` None skips balance check | `execution_engine.py:546` | Balance protection can be bypassed |

---

## Recommended Fix Priority

1. **P0-1:** Change `is False` to `not` at `execution_engine.py:599` — one-line fix, eliminates the most dangerous gap
2. **P0-3 + P0-2:** Add safety limit keys to `select_executor()` config dict, with sensible defaults from env vars
3. **P0-5:** Add entry order cancellation on SL/TP failure in `LiveExecutor.execute()`
4. **P0-4:** Import and wire `PortfolioCircuitBreaker` into `LiveExecutor.__init__()` and check before each trade
5. **P1-1:** Change `KUCOIN_USE_SANDBOX` default to `"true"` (fail-closed)
6. **P1-6:** Add `LIVE_TRADING` and `KUCOIN_USE_SANDBOX` to `.env.example`
7. **P1-5:** Remove or wire `EXECUTION_MODE` env var from Docker files
8. **P1-4:** Unify mode selection into a single codepath

---

**Derived from:** Full code audit of `src/execution/`, `src/risk/`, `src/monitoring/`, `src/config.py`, `config/.env.example`, `Dockerfile`, `docker-compose.yml`  
**Cross-referenced with:** `governance/SAFETY.md` v1.0.0 (2026-05-16)
