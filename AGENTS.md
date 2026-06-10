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
- Inbox: `S:/Archivist-Agent/lanes/kucoin/inbox/`
- Outbox: `S:/Archivist-Agent/lanes/kucoin/outbox/`
- SESSION_STATE path: `lanes/kucoin/inbox/SESSION_STATE.json`
- SESSION_STATE is written on every runtime heartbeat transition (startup, pre-cycle, post-cycle, error, sleeping, shutdown)
- SESSION_STATE includes required contract fields: `lane`, `cycle`, `timestamp`, `mode`, `status`, `phase`, `final`

## Governance
- Follows GLOBAL_GOVERNANCE.md (7 universal laws)
- Control-Plane escalation via Archivist
- OUTPUT_PROVENANCE on all artifacts

## Security
- API credentials via environment variables ONLY
- `.env` files in `.gitignore`
- No plaintext secrets in code

## Anchored Summary

### Goal
Build a complete trading pipeline for both:
1. **DEX Pre-Launch**: Track new Solana tokens (Pump.fun, Birdeye, DexScreener) before listing
2. **KuCoin Trading**: Execute trades on already-listed pairs

### Constraints & Preferences
(none)

### Progress
#### Done
- Added root-level `conftest.py` that inserts the repository root into `sys.path` for all test runs.
- Implemented `pytest_ignore_collect` in `conftest.py` to skip live-API example scripts and backup/workspace files.
- Created `pytest.ini` with `testpaths = tests` to restrict discovery to the official test directory.
- Deleted stale `__pycache__` directories to eliminate import mismatch errors.
- Verified that **all tests now pass**: `669 passed, 2 skipped`.
- Created `src/intelligence/trading_decision.py` with `make_trade_decisions()` function that converts enriched pre-launch token signals into buy decisions.
- Added comprehensive unit tests in `tests/intelligence/test_trading_decision.py` (12 tests, all passing).
- Created `run_pipeline.py` orchestrator with pre-launch scanning and watchlist generation.
- Added `src/execution/dex_jupiter_executor.py` for DEX paper trading on Solana tokens.
- Added `tests/execution/test_dex_jupiter_executor.py` (5 tests, all passing).

#### In Progress
- **KuCoin Trading**: `LiveExecutor` exists but `run_pipeline.py` doesn't connect to it yet for already-listed pairs.

#### Blocked
(none)

### Key Decisions
- Use a top-level `conftest.py` for global `sys.path` injection.
- Skip heavy or network-dependent test files early via `pytest_ignore_collect`.
- Limit collection to the `tests` folder via `pytest.ini`.
- Keep the simplified reputation calculation for creators.

### Next Steps
- **KuCoin Trading**: Wire `run_pipeline.py` to call `LiveExecutor.execute()` for already-listed pairs.
- **Real DEX Trading**: Replace Jupiter stub with actual API calls + Solana wallet signing.
- Continue extending intelligence modules while keeping test suite green.

### Critical Context
- Import path issues were resolved by the root `conftest.py` sys.path hack.
- `__pycache__` removal stopped "import file mismatch" errors from duplicate workspaces.
- The ignore logic prevents the one live-API script from being collected, eliminating network timeouts.
- The `RequestsDependencyWarning` about urllib3/chardet versions is harmless and does not affect test outcomes.

### Relevant Files
- `conftest.py` (root): adds repo root to `sys.path` and defines `pytest_ignore_collect` to skip example scripts and backup/workspace files.
- `pytest.ini`: sets `testpaths = tests` to constrain discovery to the proper test tree.
- `src/intelligence/trading_decision.py`: provides `make_trade_decisions()` for converting pre-launch token signals to trade actions.
- `tests/intelligence/test_trading_decision.py`: 12 unit tests for the trading decision module.
- `src/execution/dex_jupiter_executor.py`: DEX paper trading executor for Solana tokens (Jupiter stub).
- `tests/execution/test_dex_jupiter_executor.py`: 5 unit tests for DEX executor.
- `run_pipeline.py`: main orchestrator that ties together scanning, decisions, and execution.
- `src/intelligence/chain/prelaunch_scanner.py`: scans Pump.fun, Birdeye, DexScreener for new tokens.
- `src/execution/execution_engine.py`: `LiveExecutor` for KuCoin trades, `DryRunExecutor` for backtesting.
