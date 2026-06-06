# KuCoin Lane: Local vs Headless Sync & MEV Bot Cross-Reference

**Generated:** 2026-05-30  
**Author:** Kilo agent analysis

---

## 1. Local vs Headless Sync Status

### Git Commits: IDENTICAL

Both local (`S:\kucoin-lane`) and headless (`/home/we4free/agent/repos/kucoin-lane`) are at the same commit:

```
5910960 feat: add HistoricalBacktester with klines data, intelligence signal boosting
```

Branch: `main` on both.

### Uncommitted Differences (Headless is AHEAD)

The headless agent autonomously built a paper trade ledger feature that has **not** been committed or synced back to local:

| File | Status | Lines | Purpose |
|------|--------|-------|---------|
| `src/trading/paper_trade_ledger.py` | New | 468 | Persistent paper trade tracking with edge validation statistics |
| `src/trading/__init__.py` | New | ~15 | Module init |
| `scripts/paper_trade_runner.py` | New | ~500 | Rapid historical simulation runner using klines data |
| `src/execution/execution_engine.py` | Modified | ~70 lines added | Wires PaperTradeLedger into DryRunExecutor — opens/closes trades, monitors positions against live prices |
| `paper_trades_ledger.json` | Untracked | — | Live ledger data (3.3KB) |
| `paper_trades_ledger_report.txt` | Untracked | — | Generated report |
| `paper_trades_ledger_sim_config.json` | Untracked | — | Sim config |

**Local is clean** — no uncommitted changes, no `src/trading/` directory.

### Verdict

The local copy is behind the headless by the paper trade ledger feature. The headless agent built this autonomously and it hasn't been committed or synced back yet. The committed codebase is identical.

---

## 2. FreeAgent MEV Bot Analysis (Archived)

Location: `S:\_ARCHIVED\abandoned-projects\FreeAgent\`

### Architecture: 5-Layer Pipeline

```
SignalLayer → ValidationLayer → RiskLayer → ExecutionLayer → PostTradeLayer
```

### Key Files

| File | Purpose | Completeness |
|------|---------|-------------|
| `arbitrage_engine.py` (343 lines) | Cross-exchange spread detection via ccxt, 100ms scan loop, confidence scoring | **Most complete** — working ccxt integration |
| `mythtech_arbitrage_pipeline.py` (59 lines) | Orchestrates the full 5-layer flow | Complete skeleton |
| `signal_layer.py` (41 lines) | Cross-exchange spread detection (best-ask/best-bid across venues) | Working but basic |
| `validation_layer.py` (29 lines) | Fee/slippage cost filtering | **Valuable pattern** — rejects if spread < 2*fee + slippage |
| `risk_layer.py` (28 lines) | Exposure limits (2% max), correlation checks, fixed-fractional sizing | Basic but sound |
| `execution_layer.py` (27 lines) | Execution strategy (single-shot/sliced/hedged) | Placeholder only |
| `post_trade_layer.py` (33 lines) | PnL reconciliation, error pattern analysis, latency tracking | Good pattern, stub impl |
| `mythtech_agents.py` (49 lines) | Agent abstractions (Spreadseer, SlippageWarden, LatencyDragonfly, CircuitOracle, LedgerTitan) | Stubs only |

### What's Beneficial for KuCoin Bot

| FreeAgent Component | KuCoin Bot Gap | Benefit |
|---|---|---|
| **ValidationLayer** (fee/slippage filter) | No cost-of-trade validation before execution | Reject trades where spread < fees+slippage — prevents negative-expectancy entries |
| **SignalLayer** (cross-exchange spread detection) | Only single-exchange signals | Could detect when KuCoin price diverges from Binance/Bybit, confirming mean-reversion setups |
| **LatencyDragonfly** concept | No latency tracking | Track execution latency per trade, annotate opportunities with TTL before stale |
| **PostTradeLayer** (error pattern analysis) | No systematic error categorization | Count/classify failure modes (timeout, rejection, insufficient margin) to improve resilience |
| **ArbitrageDetector** (multi-exchange price fetch) | Only KuCoin data source | Add Binance/Bybit as reference prices for confirmation signals |
| **EnhancedRiskManager** (arb-specific limits) | Only generic risk limits | Add execution-time risk gate — reject if estimated fill time > threshold |
| **Pipeline pattern** (5-layer with early rejection) | Current pipeline allows weak signals through | Filter harder at each stage: signal → validate costs → risk check → execute |

### What's NOT Useful

Most FreeAgent files are placeholders (TODO comments, stub methods). The concepts are sound but implementations are skeletal. Direct code porting doesn't fit — the kucoin bot is single-exchange margin trading while FreeAgent targets multi-exchange arb. The **patterns** are what's valuable, not the code.

### Priority Recommendations for KuCoin Bot

1. **Cost validation gate** — Port the `ValidationLayer` fee/slippage check into the intelligence pipeline before risk approval. This is the biggest gap.
2. **Error pattern tracking** — Port `PostTradeLayer.analyze_error_patterns()` into the monitor agent.
3. **Execution latency tracking** — Add timing annotations to trades.
4. **Multi-exchange reference prices** — Expand `MultiProviderClient` to fetch Binance/Bybit prices alongside KuCoin.
