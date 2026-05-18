# KuCoin Lane — Runtime Wire Map

OUTPUT_PROVENANCE:
updated: 2026-05-18
session: kucoin-headless-01

## Wired into Runtime (called by orchestrator)

| Class | File | How |
|-------|------|-----|
| `IntelligenceOrchestrator` | `src/intelligence/orchestrator.py` | Main loop controller |
| `MonitoringAgent` | `src/monitoring/monitor_agent.py` | Called in orchestrator finally block |
| `AuditorAgent` | `src/monitoring/auditor.py` | Called in orchestrator finally block (warning-only) |
| `RiskManagementAgent` | `src/risk/risk_manager.py` | Called during risk phase |
| `ExchangeAdapter` | `src/execution/` | Via ExecutionEngine |
| `ExecutionEngine` | `src/execution/` | DryRun mode active |
| `DeterministicStartup` | `src/deterministic_startup.py` | Three-stage startup |

## Dead Code (defined + tested + exported, NOT wired into any runtime path)

| Class | File | What It Would Do |
|-------|------|-----------------|
| `CircuitBreaker` | `src/risk/circuit_breaker.py` | Loss threshold monitoring (8%/60min window) |
| `PortfolioCircuitBreaker` | `src/risk/portfolio_circuit_breaker.py` | Max drawdown 8%, max daily loss 6%, cooldown 60min |
| `KellyPositionSizer` | `src/risk/kelly_criterion.py` | Kelly-optimal position sizing (1-25%, default 10%) |

## Current Safety State
- `circuit_breaker_active` is a simple in-memory bool in orchestrator
- Circuit breaker activates on: manual call only (from pause_trading, activate_circuit_breaker methods)
- Circuit breaker does NOT activate on: audit failure, daily loss limit, drawdown threshold, position sizing violation
