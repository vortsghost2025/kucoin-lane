# KuCoin Lane — Trading Lane

## Identity
KuCoin margin trading bot. Autonomous, self-healing, self-upgrading.

## Architecture
Mirrors `vortsghost2025/kucoin-margin-bot` with ensemble agent logic merged in.

```
src/
  intelligence/     Regime, LeadLag, WhaleWatch, Orchestrator
  execution/        ExchangeAdapter (ABC), ExecutionEngine (DryRun/Live)
  risk/             CircuitBreaker, PortfolioCircuitBreaker, KellyCriterion, RiskManager
  monitoring/       MonitorAgent, PrometheusMetrics
  data/             MultiProviderClient, CoinGeckoClient, DataFetcher
  base_agent.py     AgentStatus, BaseAgent (from ensemble)
  entry_timing.py   Reversal confirmation logic
  deterministic_startup.py  Three-stage startup
  checkpoint_manager.py     State checkpointing
  config.py         Environment-variable-only config (NO hardcoded creds)
config/
  .env.example      Template with all required env vars
  coin_parameters.json
governance/
  ROLES.md
  COORDINATION.md
  SAFETY.md
  lane-relay.json   Inbox paths for Archivist relay
tests/
docker-compose.yml
Dockerfile
```

## Lane-Relay
- Inbox: `S:/Archivist-Agent/inbox/kucoin-lane/`
- Outbox: `S:/Archivist-Agent/outbox/kucoin-lane/`
- SESSION_STATE.json written every cycle

## Governance
- Follows GLOBAL_GOVERNANCE.md (7 universal laws)
- Control-Plane escalation via Archivist
- OUTPUT_PROVENANCE on all artifacts

## Security
- API credentials via environment variables ONLY
- `.env` files in `.gitignore`
- No plaintext secrets in code
