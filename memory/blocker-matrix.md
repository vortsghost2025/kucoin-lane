# KuCoin Lane — Go-Live Blocker Matrix

OUTPUT_PROVENANCE:
  agent: archivist
  lane: archivist
  generated_at: 2026-05-20T20:33:00-04:00
  session_id: kucoin-activation-03

| ID | Blocker | Severity | File(s) | Description | Status | Notes |
|----|---------|----------|---------|-------------|--------|-------|
| B1 | No kucoin-lane systemd service | HIGH | N/A | Lane won't auto-start on boot. 4 monitoring timers exist but no lane service. | OPEN | Create `kucoin-lane.service` in `ops/systemd/`; model after existing monitoring timers |
| B2 | CircuitBreaker .is_triggered() missing | HIGH→FIXED | `circuit_breaker.py`, `portfolio_circuit_breaker.py`, `execution_engine.py` | execution_engine calls `.is_triggered()` but both CB classes only had attributes (`.is_tripped`, `.tripped`). Would cause `AttributeError` at runtime. CB was ALREADY wired into orchestrator (not dead code). | **FIXED** | Added `is_triggered()` method to both classes. Orchestrator already imports/instantiates/checks PortfolioCircuitBreaker at lines 34, 107-110, 872-874 |
| B3 | Auditor failures warning-only | MEDIUM→DONE | `orchestrator.py:867-868` | Auditor now calls `activate_circuit_breaker()` on audit violation. | **DONE** | Already fixed in current code. Line 867-868: `self.activate_circuit_breaker(f"Audit failed: {violation_summary}")` |
| B4 | No API keys configured | HIGH | `.env` (missing) | Required for any non-dry-run mode. | OPEN | Expected for dry-run; add keys before go-live |
| B5 | deterministic_startup requires .env | LOW | `src/deterministic_startup.py:176-206` | Startup warns without .env but proceeds with defaults in dry-run. | CLARIFIED | Not a true blocker for dry-run |
| B6 | asset_configs hardcoded for 3 pairs | LOW | `src/risk/risk_manager.py:76-92` | SOL/BTC/ETH only. Adding pair requires code change. | OPEN | Low priority; externalize to JSON config when needed |
| B7 | circuit_breaker_active in-memory only | MEDIUM→FIXED | `orchestrator.py:100,163-168` | No persistence. Restart resets it. PortfolioCircuitBreaker already had persistence. | **FIXED** | Added `_load_cb_state()` / `_persist_cb_state()` / `reset_circuit_breaker()` methods. State written to `cb_state.json`, loaded on init. |

## Accepted Non-Blockers

| Item | Rationale |
|------|-----------|
| No CoinGecko API key | Optional; dry-run works without it |
| No Telegram config | Optional; gracefully skipped |
| sys.path.insert(0,...) in risk_manager.py | Works but fragile; low priority |
| SIGKILL crash write gap | SIGTERM/SIGINT handled; SIGKILL is edge case |
| B5 deterministic_startup .env warning | Works with defaults in dry-run; verification warns but does not halt |
| KellyPositionSizer not wired | Only in `__init__.py` and tests; not instantiated in runtime. Optional enhancement, not a blocker |
