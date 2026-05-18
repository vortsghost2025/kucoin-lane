# KuCoin Lane

Autonomous margin trading bot for KuCoin. Self-healing, self-upgrading, governed by a 4-role agent ensemble.

## Status

| Item | State |
|------|-------|
| Execution mode | `dry_run` (no live trading) |
| Test suite | 302 passing |
| Go-live blockers | 7 OPEN (see [blocker-matrix.md](memory/blocker-matrix.md)) |
| Circuit breaker classes | Defined + tested, NOT wired into runtime |
| Bot status | `shutdown` (no active cycles) |

## Architecture

4-role ensemble — agents exchange artifacts through shared state and structured logs, never direct calls.

```
Market Data
  ↓
Intelligence Agents (RegimeDetector, LeadLag, WhaleWatch, MarketAnalyzer)
  ↓
Orchestrator (trade decision + confidence)
  ↓
RiskManager (APPROVED / REJECTED / REDUCED + position size + stops)
  ↓
Executor (order placement + fill)
  ↓
Monitor (event log)
  ↓
Auditor (post-cycle verification)
  ↓
CheckpointManager (state persistence)
  ↓
[Next cycle]
```

### Source Layout

```
src/
  intelligence/     RegimeDetector, LeadLag, WhaleWatch, Orchestrator
  execution/        ExchangeAdapter (ABC), ExecutionEngine (DryRun/Live)
  risk/             CircuitBreaker*, PortfolioCircuitBreaker*, KellyCriterion*, RiskManager
  monitoring/       MonitorAgent, AuditorAgent
  data/             MultiProviderClient, CoinGeckoClient, DataFetcher
  base_agent.py     AgentStatus, BaseAgent
  entry_timing.py   Reversal confirmation logic
  deterministic_startup.py  Three-stage startup (CLEANUP → INIT → VERIFY)
  checkpoint_manager.py     State checkpointing
  config.py         Environment-variable-only config
config/
  .env.example      Template with all required env vars
  coin_parameters.json
governance/
  ROLES.md          4-role definitions, boundaries, interoperability matrix
  COORDINATION.md   Coordination protocol, state machine, handoff triggers
  SAFETY.md         Fallback rules, escalation paths, emergency procedures
  lane-relay.json   Inbox paths for Archivist relay
tests/              302 tests (pytest)
```

\* Defined, exported, and tested but **NOT wired into runtime**. See [wire-map.md](memory/wire-map.md).

## Quick Start

```bash
cp config/.env.example .env
# Edit .env with your values (or leave defaults for dry-run)

pip install -r requirements.txt
pytest tests/ -q                  # verify test suite
EXECUTION_MODE=dry_run python -m src.deterministic_startup
```

## Configuration

All configuration is via environment variables. No hardcoded credentials.

| Variable | Purpose | Default |
|----------|---------|---------|
| `EXECUTION_MODE` | `dry_run` or `live` | `dry_run` |
| `KUCOIN_API_KEY` | KuCoin API key | (required for live) |
| `KUCOIN_API_SECRET` | KuCoin API secret | (required for live) |
| `KUCOIN_PASSPHRASE` | KuCoin API passphrase | (required for live) |
| `COINGECKO_API_KEY` | CoinGecko Pro API key | (optional) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | (optional) |
| `TELEGRAM_CHAT_ID` | Telegram chat ID | (optional) |

See `config/.env.example` for the complete list.

## Monitoring

| Artifact | Path | Cadence |
|----------|------|---------|
| SESSION_STATE | `lanes/kucoin/inbox/SESSION_STATE.json` | Every cycle |
| Heartbeat | `bot_heartbeat_dry_run.json` | Every cycle |
| Hourly snapshots | `lanes/kucoin/state/monitoring/hourly_snapshots.jsonl` | Hourly (systemd timer) |
| Derived views | `docs/automation/latest-monitoring-*.md` | On demand |

## Governance

- Follows 7 universal governance laws (see parent ensemble)
- Lane-relay inbox: `lanes/kucoin/inbox/` (signed JSON messages)
- SESSION_STATE contract: `governance/lane-relay.json`
- OUTPUT_PROVENANCE on all artifacts

## Documentation

| File | Purpose |
|------|---------|
| [AGENTS.md](AGENTS.md) | Lane identity, architecture tree, lane-relay contract |
| [governance/ROLES.md](governance/ROLES.md) | 4-role definitions and boundaries |
| [governance/COORDINATION.md](governance/COORDINATION.md) | Coordination protocol and state machine |
| [governance/SAFETY.md](governance/SAFETY.md) | Fallback rules, escalation, emergency procedures |
| [docs/OPERATIONS_RUNBOOK.md](docs/OPERATIONS_RUNBOOK.md) | Start/stop/monitor operations guide |
| [docs/HEAD_DEPARTMENT_VERDICT.md](docs/HEAD_DEPARTMENT_VERDICT.md) | 8-mission operator manual (narrative) |
| [docs/SAFETY_BOUNDARIES.md](docs/SAFETY_BOUNDARIES.md) | Implementation-level safety boundary audit |
| [memory/key-findings.md](memory/key-findings.md) | Accumulated architecture truths (canonical structured source) |
| [memory/blocker-matrix.md](memory/blocker-matrix.md) | Live go-live blocker matrix |
| [memory/wire-map.md](memory/wire-map.md) | Runtime wire map (wired vs dead code) |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

### Documentation Relationship Map

```
memory/ (canonical structured truth)
  ├── key-findings.md  ←── verified facts, the source of truth
  ├── blocker-matrix.md ←── live blocker status
  └── wire-map.md       ←── runtime wiring state

docs/ (narrative + operational)
  ├── HEAD_DEPARTMENT_VERDICT.md  ←── narrative version of memory/ + operator manual
  ├── SAFETY_BOUNDARIES.md        ←── implementation audit (complements governance/SAFETY.md)
  ├── OPERATIONS_RUNBOOK.md       ←── how-to operations guide
  └── KUCOIN_LANE_TRUTH_MAP.md    ←── provenance-tagged truth map

governance/ (prescriptive)
  ├── ROLES.md          ←── what roles exist and their boundaries
  ├── COORDINATION.md   ←── how roles interact (state machine)
  └── SAFETY.md         ←── safety rules and emergency procedures
```

**Rule:** `memory/` is the canonical structured source. `docs/HEAD_DEPARTMENT_VERDICT.md` is the narrative companion. When they conflict, `memory/` wins. Update both when making changes.

## Go-Live Blockers

| ID | Blocker | Severity |
|----|---------|----------|
| B1 | No systemd service | HIGH |
| B2 | CircuitBreaker classes dead code | HIGH |
| B3 | Auditor failures warning-only | MEDIUM |
| B4 | No API keys configured | HIGH |
| B5 | deterministic_startup requires .env | LOW |
| B6 | asset_configs hardcoded for 3 pairs | LOW |
| B7 | circuit_breaker_active in-memory only | MEDIUM |

See [memory/blocker-matrix.md](memory/blocker-matrix.md) for details and resolution status.
