# KuCoin Lane — Go-Live Blocker Matrix

OUTPUT_PROVENANCE:
updated: 2026-05-18
session: kucoin-headless-01

| ID | Blocker | Severity | File(s) | Description | Status | Notes |
|----|---------|----------|---------|-------------|--------|-------|
| B1 | No kucoin-lane systemd service | HIGH | N/A | Lane won't auto-start on boot. 4 monitoring timers exist but no lane service. | OPEN | Create `kucoin-lane.service` in `ops/systemd/`; model after existing monitoring timers |
| B2 | CircuitBreaker classes dead code | HIGH | `src/risk/circuit_breaker.py`, `portfolio_circuit_breaker.py`, `kelly_criterion.py` | Defined, exported, tested — never wired into runtime. Formal safety layer doesn't execute. | OPEN | Wire into Orchestrator cycle; see `memory/wire-map.md` |
| B3 | Auditor failures warning-only | MEDIUM | `src/intelligence/orchestrator.py:841-853` | Governance says activate circuit breaker. Runtime only logs. | OPEN | Depends on B2 resolution; auditor should call CB trip |
| B4 | No API keys configured | HIGH | `.env` (missing) | Required for any non-dry-run mode. | OPEN | Expected for dry-run; add keys before go-live |
| B5 | deterministic_startup requires .env | LOW | `src/deterministic_startup.py:176-206` | Startup warns without .env but proceeds with defaults in dry-run. | CLARIFIED | Not a true blocker for dry-run; verification step logs warning but does not halt. Demote to non-blocker if dry-run is primary mode. |
| B6 | asset_configs hardcoded for 3 pairs | LOW | `src/risk/risk_manager.py:76-92` | SOL/BTC/ETH only. Adding pair requires code change. | OPEN | Low priority; externalize to JSON config when needed |
| B7 | circuit_breaker_active in-memory | MEDIUM | `src/intelligence/orchestrator.py` | No persistence. Restart resets it. | OPEN | Persist to checkpoint file alongside SESSION_STATE |

## Accepted Non-Blockers

| Item | Rationale |
|------|-----------|
| No CoinGecko API key | Optional; dry-run works without it |
| No Telegram config | Optional; gracefully skipped |
| sys.path.insert(0,...) in risk_manager.py | Works but fragile; low priority |
| SIGKILL crash write gap | SIGTERM/SIGINT handled; SIGKILL is edge case |
| B5 deterministic_startup .env warning | Works with defaults in dry-run; verification warns but does not halt |
