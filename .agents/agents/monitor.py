#!/usr/bin/env python3
"""Monitor Agent Entry Point"""

import sys
import argparse
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from context import read_context, record_anomaly, record_alert, update_api_latency

# North Star metric targets
TARGETS = {
    "win_rate": 0.55,
    "avg_roi": 0.02,
    "max_drawdown": 0.10,
    "daily_pnl_vol": 0.03,
    "scan_success_rate": 0.95,
    "api_latency_p95": 2.0,
    "sharpe_ratio": 1.5,
}

ALERT_THRESHOLDS = {
    "win_rate": 0.45,
    "avg_roi": 0.005,
    "max_drawdown": 0.15,
    "daily_pnl_vol": 0.05,
    "scan_success_rate": 0.90,
    "api_latency_p95": 5.0,
    "sharpe_ratio": 0.5,
}

def check_health(full=False):
    """Run full health check."""
    ctx = read_context()
    
    health = {
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "status": "healthy",
        "checks": {},
        "metrics": {},
        "anomalies": [],
        "alerts": [],
    }
    
    # 1. Pipeline status
    pipeline = ctx.get("pipeline", {})
    health["checks"]["pipeline"] = {
        "status": pipeline.get("status", "unknown"),
        "cycles_completed": pipeline.get("cycles_completed", 0),
        "last_cycle": pipeline.get("last_cycle_completed"),
    }
    
    # 2. Positions & P&L
    positions = ctx.get("positions", {})
    open_positions = len(positions.get("open", []))
    total_pnl = positions.get("total_pnl_usd", 0)
    win_rate = positions.get("win_rate", 0)
    total_trades = positions.get("total_trades", 0)
    
    health["metrics"] = {
        "open_positions": open_positions,
        "total_pnl_usd": total_pnl,
        "win_rate": win_rate,
        "total_trades": total_trades,
    }
    
    # Check against targets
    alerts = []
    if win_rate < ALERT_THRESHOLDS["win_rate"]:
        alerts.append({"type": "win_rate", "severity": "HIGH", "value": win_rate, "threshold": ALERT_THRESHOLDS["win_rate"]})
    if win_rate < TARGETS["win_rate"]:
        health["status"] = "degraded"
    
    # 3. Circuit breakers
    breakers = ctx.get("circuit_breakers", {})
    tripped = [k for k, v in breakers.items() if isinstance(v, dict) and v.get("tripped")]
    if tripped:
        alerts.append({"type": "circuit_breaker", "severity": "CRITICAL", "tripped": tripped})
        health["status"] = "critical"
    health["checks"]["circuit_breakers"] = {"tripped": tripped, "all": breakers}
    
    # 4. Market regime
    regime = ctx.get("market_regime", {})
    health["checks"]["market_regime"] = regime
    if regime.get("classification") == "volatile" and regime.get("confidence", 0) < 0.5:
        health["status"] = "degraded"
    
    # 5. Scan success rates
    scan_results = ctx.get("scan_results", {})
    scan_health = {}
    for source, data in scan_results.items():
        tokens = len(data.get("tokens", []))
        errors = len(data.get("errors", []))
        success = tokens > 0 or errors == 0
        scan_health[source] = {"tokens": tokens, "errors": errors, "healthy": success}
        if not success:
            alerts.append({"type": "scan_failure", "severity": "HIGH", "source": source})
            health["status"] = "degraded"
    health["checks"]["scan_sources"] = scan_health
    
    # 6. API latency
    api_latency = ctx.get("health", {}).get("api_latency", {})
    for service, latencies in api_latency.items():
        if latencies:
            recent = latencies[-10:]
            avg_lat = sum(l["latency_ms"] for l in recent) / len(recent)
            p95 = sorted(l["latency_ms"] for l in recent)[int(len(recent) * 0.95)]
            if p95 > ALERT_THRESHOLDS["api_latency_p95"] * 1000:
                alerts.append({"type": "api_latency", "severity": "HIGH", "service": service, "p95_ms": p95})
    
    # 7. Sharpe ratio (from closed positions)
    closed = ctx.get("positions", {}).get("closed_recent", [])
    if len(closed) >= 10:
        returns = [c.get("pnl_usd", 0) / 1000 for c in closed[-30:]]  # normalize to 1k capital
        import statistics
        if len(returns) > 1:
            mean_r = statistics.mean(returns)
            std_r = statistics.stdev(returns)
            sharpe = (mean_r / std_r) * (30 ** 0.5) if std_r > 0 else 0
            health["metrics"]["sharpe_ratio"] = sharpe
            if sharpe < ALERT_THRESHOLDS["sharpe_ratio"]:
                alerts.append({"type": "sharpe_ratio", "severity": "HIGH", "value": sharpe})
    
    # Record alerts
    for alert in alerts:
        record_alert(alert)
        if alert.get("severity") == "CRITICAL" and health["status"] != "critical":
            health["status"] = "critical"
        elif alert.get("severity") == "HIGH" and health["status"] == "healthy":
            health["status"] = "degraded"
    
    health["alerts"] = alerts
    health["anomalies"] = ctx.get("health", {}).get("anomalies", [])[-10:]
    
    return health

def get_pnl(period="24h"):
    """Get P&L report for period."""
    ctx = read_context()
    closed = ctx.get("positions", {}).get("closed_recent", [])
    
    # Filter by period (simplified - would use timestamps in production)
    recent = closed[-50:]
    
    total_pnl = sum(c.get("pnl_usd", 0) for c in recent)
    wins = [c for c in recent if c.get("pnl_usd", 0) > 0]
    losses = [c for c in recent if c.get("pnl_usd", 0) <= 0]
    
    return {
        "period": period,
        "total_pnl_usd": sum(c.get("pnl_usd", 0) for c in recent),
        "trade_count": len(recent),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(recent) if recent else 0,
        "avg_win": statistics.mean([c["pnl_usd"] for c in wins]) if wins else 0,
        "avg_loss": statistics.mean([c["pnl_usd"] for c in losses]) if losses else 0,
        "profit_factor": abs(sum(c["pnl_usd"] for c in wins) / sum(c["pnl_usd"] for c in losses)) if losses else float('inf'),
    }

def get_anomalies(since="1h"):
    """Get recent anomalies."""
    ctx = read_context()
    return ctx.get("health", {}).get("anomalies", [])[-20:]

def export_prometheus():
    """Export Prometheus metrics."""
    ctx = read_context()
    
    positions = ctx.get("positions", {})
    pipeline = ctx.get("pipeline", {})
    regime = ctx.get("market_regime", {})
    breakers = ctx.get("circuit_breakers", {})
    
    lines = [
        f'kucoin_cycle_total {pipeline.get("cycles_completed", 0)}',
        f'kucoin_positions_open {len(positions.get("open", []))}',
        f'kucoin_pnl_usd {positions.get("total_pnl_usd", 0)}',
        f'kucoin_win_rate {positions.get("win_rate", 0)}',
        f'kucoin_market_regime{{regime="{regime.get("classification", "unknown")}"}} 1',
    ]
    
    for name, breaker in breakers.items():
        tripped = 1 if isinstance(breaker, dict) and breaker.get("tripped") else 0
        lines.append(f'kucoin_circuit_breaker_tripped{{name="{name}"}} {tripped}')
    
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Monitor Agent")
    parser.add_argument("action", choices=["health", "status", "pnl", "anomalies", "metrics"])
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--period", type=str, default="24h")
    parser.add_argument("--since", type=str, default="1h")
    parser.add_argument("--format", choices=["prometheus", "json"], default="prometheus")
    args = parser.parse_args()
    
    if args.action == "health":
        result = check_health(args.full)
    elif args.action == "status":
        result = check_health(False)
    elif args.action == "pnl":
        result = get_pnl(args.period)
    elif args.action == "anomalies":
        result = get_anomalies(args.since)
    elif args.action == "metrics":
        if args.format == "prometheus":
            print(export_prometheus())
            return
        result = check_health(False)
    
    print(json.dumps(result, indent=2, default=str))

import statistics

if __name__ == "__main__":
    main()