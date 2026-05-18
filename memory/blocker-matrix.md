# KuCoin Lane — Go-Live Blocker Matrix

OUTPUT_PROVENANCE:
updated: 2026-05-18
session: kucoin-headless-01

| ID | Blocker | Severity | File(s) | Description | Status |
|----|---------|----------|---------|-------------|--------|
| B1 | No kucoin-lane systemd service | HIGH | N/A | Lane won't auto-start on boot. 4 monitoring timers exist but no lane service. | OPEN |
| B2 | CircuitBreaker classes dead code | HIGH | `src/risk/circuit_breaker.py`, `portfolio_circuit_breaker.py`, `kelly_criterion.py` | Defined, exported, tested — never wired into runtime. Formal safety layer doesn't execute. | OPEN |
| B3 | Auditor failures warning-only | MEDIUM | `src/intelligence/orchestrator.py:841-853` | Governance says activate circuit breaker. Runtime only logs. | OPEN |
| B4 | No API keys configured | HIGH | `.env` (missing) | Required for any non-dry-run mode. | OPEN |
| B5 | deterministic_startup requires .env | LOW | `src/deterministic_startup.py:176-206` | Startup fails verification without .env or env vars. | OPEN |
| B6 | asset_configs hardcoded for 3 pairs | LOW | `src/risk/risk_manager.py:76-92` | SOL/BTC/ETH only. Adding pair requires code change. | OPEN |
| B7 | circuit_breaker_active in-memory | MEDIUM | `src/intelligence/orchestrator.py` | No persistence. Restart resets it. | OPEN |

## Accepted Non-Blockers

| Item | Rationale |
|------|-----------|
| No CoinGecko API key | Optional; dry-run works without it |
| No Telegram config | Optional; gracefully skipped |
| sys.path.insert(0,...) in risk_manager.py | Works but fragile; low priority |
| SIGKILL crash write gap | SIGTERM/SIGINT handled; SIGKILL is edge case |
