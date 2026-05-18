# KuCoin Lane — Key Findings (Memory Bank)

OUTPUT_PROVENANCE:
updated: 2026-05-18
session: kucoin-headless-01
status: observational pass complete, no mutations

---

## Architecture Truths

### AuditorAgent (`src/monitoring/auditor.py`)
- Detects: downtrend pattern, risk enforcement failures, position sizing violations
- Failure mode: logs `logger.critical()`, returns `audit_passed=False` with `success=True`
- Orchestrator (`orchestrator.py:841-853`): calls in `finally` block, checks `audit_passed`, logs CRITICAL — but does **NOT** activate circuit breaker
- **Governance mismatch:** ROLES.md:187-189 says audit failure should hard-block. Runtime is warning-only.
- **Fix needed:** `orchestrator.py:848` — add `self.activate_circuit_breaker(f"Audit failed: {violation_summary}")`

### Risk Classes — Dead Code
Three classes are defined, exported, and tested but **never instantiated in any runtime path**:
1. `CircuitBreaker` (`src/risk/circuit_breaker.py`)
2. `PortfolioCircuitBreaker` (`src/risk/portfolio_circuit_breaker.py`)
3. `KellyPositionSizer` (`src/risk/kelly_criterion.py`)

Wired alternative: `RiskManagementAgent` (`src/risk/risk_manager.py`) — hardcoded asset_configs for SOL/BTC/ETH only, uses `sys.path.insert(0,...)` hack at line 12.

Orchestrator uses in-memory `circuit_breaker_active` boolean — no persistence, no formal class backing.

### SESSION_STATE Contract
- Write path: `ExecutionEngine.write_heartbeat() → write_session_state() → _resolve_session_state_contract() → lanes/kucoin/inbox/SESSION_STATE.json`
- Contract: `governance/lane-relay.json` defines path as `lanes/kucoin/inbox/SESSION_STATE.json` ✓
- Fields present: lane, cycle, timestamp, mode, status, phase, final, step, pid ✓
- SIGKILL gap: last heartbeat lost. SIGTERM/SIGINT handled by CheckpointManager.

### Monitoring Artifacts Hierarchy
1. **Formal state:** SESSION_STATE.json (written by ExecutionEngine every cycle)
2. **Breadcrumb:** bot_heartbeat_dry_run.json (same cadence, simpler format)
3. **Historical:** hourly_snapshots.jsonl (systemd timer, hourly)
4. **Derived views:** latest-monitoring-snapshot.md, MONITORING_ANALYSIS_daily*.md
5. **Operator context:** agent-logs/* (gitignored, not relayed to Archivist)

### Go-Live Blockers
| ID | Blocker | Severity | Status |
|----|---------|----------|--------|
| B1 | No systemd service for kucoin-lane | HIGH | Open |
| B2 | CircuitBreaker/PortfolioCircuitBreaker dead code | HIGH | Open |
| B3 | Auditor failures warning-only vs governance | MEDIUM | Open |
| B4 | No API keys configured | HIGH | Open (expected for dry-run) |
| B5 | deterministic_startup.py requires .env | LOW | Open |
| B6 | asset_configs hardcoded for 3 pairs | LOW | Open |
| B7 | circuit_breaker_active in-memory only | MEDIUM | Open |

### Test Baseline
- `venv/bin/pytest tests/ -q` — **302 passing**
- All imports verified: auditor, risk_manager, circuit_breaker, portfolio_circuit_breaker, kelly_criterion, orchestrator

---

## Session Continuity

### Heartbeat Entries (kucoin-session-heartbeats.jsonl)
1. `2026-05-17T22:35:36Z` — repo state audit + infra setup
2. `2026-05-17T22:40:00Z` — config + module import verification
3. `2026-05-17T22:55:00Z` — governance review + daily analysis + final hand
4. `2026-05-17T23:08:00Z` — dry-run cycle + monitoring snapshot
5. `2026-05-17T23:40:00Z` — readiness pass: auditor semantics + risk config + session durability + monitoring map + blocker matrix

### Last Known Good State
- Session state: `SESSION_STATE.json` written with final=true at end of Cycle 4
- Monitoring snapshot: `latest-monitoring-snapshot.md` current as of 2026-05-16T23:43:17Z
- All tests: 302 passing
- Git: clean main branch, no uncommitted changes

---

## Loaded Documents
- S:/kucoin-lane/docs/kucoinheadless.txt — 8-mission advisory (532 lines)
  - MISSION 1: System map
  - MISSION 2: New laptop → full ops workflow
  - MISSION 3: Security & safety doctrine
  - MISSION 4: Multi-plane workflow
  - MISSION 5: Tool-call error handling
  - MISSION 6: Monitoring stack
  - MISSION 7: Gap analysis
  - MISSION 8: Head-department verdict
