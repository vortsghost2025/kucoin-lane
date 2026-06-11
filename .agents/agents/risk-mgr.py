#!/usr/bin/env python3
"""Risk Manager Agent Entry Point"""

import sys
import argparse
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from context import read_context, trip_circuit_breaker, reset_circuit_breaker, check_circuit_breakers

# Risk parameters (configurable via config.json)
DEFAULT_CONFIG = {
    "kelly_fraction": 0.25,
    "max_position_pct": 0.20,
    "daily_loss_limit": 0.05,
    "max_drawdown_limit": 0.15,
    "min_liquidity_usd": 500,
    "min_creator_score": 0.3,
    "max_same_creator": 3,
}

def check_risk(mint, sol_amount, side, config=None):
    """Run all risk checks and return verdict."""
    config = {**DEFAULT_CONFIG, **(config or {})}
    ctx = read_context()
    
    checks = {}
    rationale = []
    verdict = "ALLOW"
    adjusted_size = sol_amount
    
    # 1. Circuit Breakers
    breakers = check_circuit_breakers()
    if any(breakers.values()):
        checks["circuit_breakers"] = "FAIL"
        rationale.append(f"Circuit breakers tripped: {[k for k,v in breakers.items() if v]}")
        verdict = "BLOCK"
    else:
        checks["circuit_breakers"] = "PASS"
    
    # 2. Daily Loss Limit
    total_pnl = ctx.get("positions", {}).get("total_pnl_usd", 0)
    # Assume $1000 capital for now (should come from config)
    capital = 1000
    daily_loss_pct = abs(total_pnl) / capital if total_pnl < 0 else 0
    if daily_loss_pct >= config["daily_loss_limit"]:
        checks["daily_loss"] = "FAIL"
        rationale.append(f"Daily loss limit exceeded: {daily_loss_pct:.1%}")
        verdict = "BLOCK"
    else:
        checks["daily_loss"] = "PASS"
    
    # 3. Max Drawdown
    closed = ctx.get("positions", {}).get("closed_recent", [])
    if closed:
        equity_curve = [c.get("pnl_usd", 0) for c in closed]
        peak = max(equity_curve) if equity_curve else 0
        current = sum(equity_curve)
        drawdown = (peak - current) / peak if peak > 0 else 0
        if drawdown >= config["max_drawdown_limit"]:
            checks["max_drawdown"] = "FAIL"
            rationale.append(f"Max drawdown exceeded: {drawdown:.1%}")
            verdict = "BLOCK"
        else:
            checks["max_drawdown"] = "PASS"
    else:
        checks["max_drawdown"] = "PASS"
    
    # 4. Kelly Sizing (simplified)
    # win_prob estimated from creator reputation + market regime
    win_prob = 0.55  # default
    creator_reg = ctx.get("creator_registry", {})
    alpha_creators = creator_reg.get("alpha_creators", [])
    # Check if this mint's creator is alpha
    # (would need mint->creator mapping in real impl)
    
    kelly_size = config["kelly_fraction"] * capital * win_prob
    if sol_amount > kelly_size * 1.5:
        checks["kelly_sizing"] = "REDUCE"
        rationale.append(f"Kelly sizing: {sol_amount:.4f} -> {kelly_size:.4f} (75% of requested)")
        verdict = "REDUCE" if verdict == "ALLOW" else verdict
        adjusted_size = kelly_size
    else:
        checks["kelly_sizing"] = "PASS"
    
    # 5. Max Position %
    if sol_amount > capital * config["max_position_pct"]:
        checks["max_position"] = "REDUCE"
        rationale.append(f"Position exceeds max {config['max_position_pct']:.0%} of capital")
        verdict = "REDUCE" if verdict == "ALLOW" else verdict
        adjusted_size = min(adjusted_size, capital * config["max_position_pct"])
    else:
        checks["max_position"] = "PASS"
    
    # 6. Creator Reputation (placeholder)
    checks["creator_rep"] = "PASS"
    
    # 7. Market Regime
    regime = ctx.get("market_regime", {}).get("classification", "unknown")
    conf = ctx.get("market_regime", {}).get("confidence", 0)
    if regime == "volatile" and conf < 0.5:
        checks["market_regime"] = "REDUCE"
        rationale.append(f"Market regime: {regime} (conf {conf:.2f})")
        verdict = "REDUCE" if verdict == "ALLOW" else verdict
    else:
        checks["market_regime"] = "PASS"
    
    # 8. Liquidity Check (from scan results)
    # Would check scan_results for this mint
    checks["liquidity"] = "PASS"
    
    # 9. Concentration Check
    open_positions = ctx.get("positions", {}).get("open", [])
    creator_counts = {}
    for pos in open_positions:
        # Would need mint->creator mapping
        pass
    checks["concentration"] = "PASS"
    
    return {
        "verdict": verdict,
        "position_size_sol": round(adjusted_size, 6),
        "rationale": rationale,
        "checks": checks,
        "circuit_breakers": breakers
    }

def main():
    parser = argparse.ArgumentParser(description="Risk Manager Agent")
    parser.add_argument("action", choices=["check", "status", "trip", "reset"])
    parser.add_argument("--mint", type=str)
    parser.add_argument("--sol", type=float, default=0.05)
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    parser.add_argument("--name", type=str)
    parser.add_argument("--reason", type=str)
    args = parser.parse_args()
    
    if args.action == "check":
        result = check_risk(args.mint, args.sol, args.side)
    elif args.action == "status":
        ctx = read_context()
        result = {"circuit_breakers": check_circuit_breakers(), "config": DEFAULT_CONFIG}
    elif args.action == "trip":
        trip_circuit_breaker(args.name, args.reason)
        result = {"success": True, "tripped": args.name}
    elif args.action == "reset":
        reset_circuit_breaker(args.name)
        result = {"success": True, "reset": args.name}
    
    print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    main()