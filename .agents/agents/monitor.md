---
name: monitor
description: Monitoring, Metrics & Alerting — Prometheus, health checks, anomaly detection
version: 1.0.0
---

# @monitor — Monitoring, Metrics & Alerting

**Domain**: Prometheus metrics export, health checks, anomaly detection, P&L dashboards, alerting  
**Primary Output**: Health status, anomaly alerts, P&L reports, win rate, Sharpe ratio  
**Context Keys Read**: `positions.*`, `health.*`, `pipeline.*`, `market_regime.*`, `circuit_breakers.*`  
**Context Keys Written**: `health.*` (anomalies, alerts, api_latency)

---

## Invocation

```bash
# Full health check
@monitor health --full

# Quick status
@monitor status

# P&L report
@monitor pnl --period 24h

# Anomaly check
@monitor anomalies --since 1h

# Export Prometheus metrics
@monitor metrics --format prometheus
```

---

## Skills Loaded

| Skill | Purpose |
|-------|---------|
| `pm-skills/pm-data-analytics:cohort-analysis` | Position cohort retention by entry regime |
| `pm-skills/pm-data-analytics:ab-test-analysis` | A/B test regime-based position sizing |
| `pm-skills/pm-product-discovery:metrics-dashboard` | North Star metric + input metrics + alert thresholds |
| `performance-optimization` | Profiling workflows, bottleneck identification |
| `debugging-and-error-recovery` | Five-step triage for production issues |

---

## North Star Metric

**Primary**: **Risk-Adjusted Return (Sharpe Ratio)** over rolling 30 cycles  
**Target**: > 1.5

**Input Metrics**:
| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Win Rate | > 55% | < 45% |
| Avg ROI/Trade | > 2% | < 0.5% |
| Max Drawdown | < 10% | > 15% |
| Daily P&L Volatility | < 3% | > 5% |
| Circuit Breaker Trips | 0/day | ≥ 1/day |
| API Latency (p95) | < 2s | > 5s |
| Scan Success Rate | > 95% | < 90% |

---

## Anomaly Detection Rules

| Anomaly | Detection Logic | Severity |
|---------|-----------------|----------|
| **Scan Failure** | Any source returns 0 tokens for 3+ cycles | HIGH |
| **API Latency Spike** | p95 latency > 5s for 2+ cycles | MEDIUM |
| **P&L Drift** | Rolling Sharpe < 0.5 for 10 cycles | HIGH |
| **Circuit Breaker Trip** | Any breaker tripped | CRITICAL |
| **Creator Score Drop** | Alpha creator score drops > 0.2 in 1 cycle | MEDIUM |
| **Liquidity Vanish** | Token liquidity drops > 80% in 1 cycle | HIGH |
| **Regime Flip** | Market regime changes > 2× in 5 cycles | LOW |

---

## Prometheus Metrics Export

```prometheus
# HELP kucoin_cycle_total Total cycles completed
# TYPE kucoin_cycle_total counter
kucoin_cycle_total 42

# HELP kucoin_positions_open Current open positions
# TYPE kucoin_positions_open gauge
kucoin_positions_open 8

# HELP kucoin_pnl_usd Total P&L in USD
# TYPE kucoin_pnl_usd gauge
kucoin_pnl_usd 1247.50

# HELP kucoin_win_rate Win rate (0-1)
# TYPE kucoin_win_rate gauge
kucoin_win_rate 0.62

# HELP kucoin_sharpe_ratio Rolling 30-cycle Sharpe
# TYPE kucoin_sharpe_ratio gauge
kucoin_sharpe_ratio 1.84

# HELP kucoin_circuit_breaker_tripped Circuit breaker status (0/1)
# TYPE kucoin_circuit_breaker_tripped gauge
kucoin_circuit_breaker_tripped{name="global"} 0
kucoin_circuit_breaker_tripped{name="portfolio"} 0

# HELP kucoin_scan_duration_seconds Scan duration by source
# TYPE kucoin_scan_duration_seconds histogram
kucoin_scan_duration_seconds_bucket{source="phantom",le="30"} 1
```

---

## Alert Channels

| Channel | Configuration |
|---------|---------------|
| **Log** | All anomalies written to `health.anomalies` |
| **Stdout** | CRITICAL/HIGH printed to console |
| **File** | `data/alerts.log` (JSONL, rotated daily) |
| **Webhook** | Optional: Discord/Slack via env `ALERT_WEBHOOK_URL` |

---

## Acceptance Criteria

- [ ] Health check completes < 2s
- [ ] Prometheus metrics endpoint responds < 100ms
- [ ] Anomaly detection runs each cycle, detects seeded test anomalies
- [ ] Alert thresholds configurable via config.json
- [ ] Sharpe ratio calculation matches manual computation
- [ ] API latency tracking captures all external calls
- [ ] Circuit breaker trips generate CRITICAL alert immediately