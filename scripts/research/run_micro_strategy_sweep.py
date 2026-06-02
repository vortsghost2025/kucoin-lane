#!/usr/bin/env python3
"""
Parameter sweep for micro-account trading strategy.

Models fee drag on a $110 account to find strategy parameters that are
profitable after friction (fees + spread + slippage).

Run: python3 scripts/research/run_micro_strategy_sweep.py
"""

import json
import os
import itertools

# ─── Friction settings ───────────────────────────────────────────────────────
ROUND_TRIP_FEE_PCT = 0.20  # 0.1% entry + 0.1% exit = 0.20% round-trip
DEFAULT_SPREAD_PCT = 0.02  # configurable spread cost
DEFAULT_SLIPPAGE_PCT = 0.05  # configurable slippage

# ─── Capital constraints ─────────────────────────────────────────────────────
CAPITAL_USD = 110.0
MIN_EDGE_PCT = 0.40  # minimum net edge (%) required to mark PASS

# ─── Account constraint: $50 per trade, max 2 concurrent longs ──────────────
POSITION_SIZE_FIXED = 50.0
MAX_CONCURRENT_POSITIONS = 2
MAX_CAPITAL_DEPLOYABLE = POSITION_SIZE_FIXED * MAX_CONCURRENT_POSITIONS  # $100

# ─── Simulation parameters ───────────────────────────────────────────────────
SIMULATION_DAYS = 30


def round_trip_friction(spread_pct: float, slippage_pct: float) -> float:
    """Total round-trip cost as a fraction (not percent)."""
    return (ROUND_TRIP_FEE_PCT + spread_pct + slippage_pct) / 100.0


def simulate(
    take_profit_pct: float,
    stop_loss_pct: float,
    win_rate: float,
    trades_per_day: float,
    spread_pct: float,
    slippage_pct: float,
) -> dict:
    """
    Simulate one parameter combination over SIMULATION_DAYS.

    Returns a dict with gross_pnl, total_fees, net_pnl, net_edge_pct, pass_fail.
    """
    total_trades = int(SIMULATION_DAYS * trades_per_day)
    wins = int(total_trades * win_rate)
    losses = total_trades - wins

    tp_fraction = take_profit_pct / 100.0
    sl_fraction = stop_loss_pct / 100.0
    friction = round_trip_friction(spread_pct, slippage_pct)

    # Gross P&L in dollars
    gross_pnl = wins * (POSITION_SIZE_FIXED * tp_fraction) - losses * (POSITION_SIZE_FIXED * sl_fraction)

    # Fees applied to each trade's notional (entry + exit each at 0.1% + spread + slippage)
    total_notional = total_trades * POSITION_SIZE_FIXED
    total_fees = total_trades * POSITION_SIZE_FIXED * friction

    net_pnl = gross_pnl - total_fees
    total_notional_traded = total_trades * POSITION_SIZE_FIXED
    net_edge_pct = (net_pnl / total_notional_traded * 100.0) if total_notional_traded > 0 else 0.0

    return {
        "take_profit_pct": take_profit_pct,
        "stop_loss_pct": stop_loss_pct,
        "win_rate": win_rate,
        "position_size_usd": POSITION_SIZE_FIXED,
        "trades_per_day": trades_per_day,
        "total_trades": total_trades,
        "gross_pnl": round(gross_pnl, 4),
        "total_fees": round(total_fees, 4),
        "net_pnl": round(net_pnl, 4),
        "net_edge_pct": round(net_edge_pct, 4),
        "pass_fail": net_edge_pct >= MIN_EDGE_PCT and net_pnl > 0,
    }


def find_fee_breakeven_win_rate(
    take_profit_pct: float,
    stop_loss_pct: float,
    trades_per_day: float,
    spread_pct: float,
    slippage_pct: float,
) -> float:
    """
    Find the minimum win_rate at which net_pnl > 0 for the given TP/SL/trades_per_day.

    net_pnl = wins * TP_notional - losses * SL_notional - total_fees > 0
    Let w = win_rate, then:
        w * TP - (1-w) * SL - friction = 0
        w * TP - SL + w * SL - friction = 0
        w * (TP + SL) = SL + friction
        w = (SL + friction) / (TP + SL)

    TP and SL here are per-trade fractional returns, so:
        tp_frac = take_profit_pct / 100
        sl_frac = stop_loss_pct / 100
        friction_frac = (ROUND_TRIP_FEE_PCT + spread_pct + slippage_pct) / 100

    win_rate >= (sl_frac + friction_frac) / (tp_frac + sl_frac)
    """
    tp_frac = take_profit_pct / 100.0
    sl_frac = stop_loss_pct / 100.0
    friction = round_trip_friction(spread_pct, slippage_pct)

    denominator = tp_frac + sl_frac
    if denominator == 0:
        return 1.0  # can't profit with zero TP and zero SL

    breakeven_wr = (sl_frac + friction) / denominator
    # Clamp to [0, 1]
    breakeven_wr = max(0.0, min(1.0, breakeven_wr))
    return round(breakeven_wr * 100.0, 2)  # return as percentage


def main():
    spread_pct = DEFAULT_SPREAD_PCT
    slippage_pct = DEFAULT_SLIPPAGE_PCT

    # ─── Parameter ranges ─────────────────────────────────────────────────────
    take_profit_vals = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
    stop_loss_vals = [1.0, 1.5, 2.0, 2.5, 3.0]
    win_rate_vals = [0.45, 0.50, 0.55, 0.60, 0.65]
    position_size_vals = [POSITION_SIZE_FIXED]  # fixed at $50 due to capital constraint
    trades_per_day_vals = [0.5, 1.0, 2.0, 3.0]

    print("=" * 90)
    print("MICRO-STRATEGY PARAMETER SWEEP")
    print(f"  Capital: ${CAPITAL_USD:.2f}  |  Position size: ${POSITION_SIZE_FIXED:.2f}")
    print(f"  Max concurrent positions: {MAX_CONCURRENT_POSITIONS}  |  Max deployable: ${MAX_CAPITAL_DEPLOYABLE:.2f}")
    print(f"  Round-trip friction: {ROUND_TRIP_FEE_PCT}% + {spread_pct}% spread + {slippage_pct}% slippage")
    print(f"  Min edge for PASS: {MIN_EDGE_PCT}%  |  Simulation: {SIMULATION_DAYS} days")
    print("=" * 90)

    # Run sweep
    results = []
    total_combos = (
        len(take_profit_vals)
        * len(stop_loss_vals)
        * len(win_rate_vals)
        * len(position_size_vals)
        * len(trades_per_day_vals)
    )
    print(f"Total combinations: {total_combos}\n")

    for tp, sl, wr, ps, tpd in itertools.product(
        take_profit_vals,
        stop_loss_vals,
        win_rate_vals,
        position_size_vals,
        trades_per_day_vals,
    ):
        result = simulate(tp, sl, wr, tpd, spread_pct, slippage_pct)
        results.append(result)

    # ─── Summary: PASS combinations ───────────────────────────────────────────
    passing = [r for r in results if r["pass_fail"]]
    failing = [r for r in results if not r["pass_fail"]]

    print(f"\n{'=' * 90}")
    print(f"PASSING COMBINATIONS ({len(passing)} / {total_combos})")
    print(f"{'=' * 90}")

    if passing:
        header = (
            f"{'TP':>5} {'SL':>5} {'WR':>6} {'TPD':>5} "
            f"{'Gross P&L':>12} {'Fees':>10} {'Net P&L':>10} {'Net Edge%':>10}"
        )
        print(header)
        print("-" * 75)
        for r in sorted(passing, key=lambda x: x["net_pnl"], reverse=True):
            print(
                f"{r['take_profit_pct']:>5.1f} {r['stop_loss_pct']:>5.1f} "
                f"{r['win_rate']:>6.2f} {r['trades_per_day']:>5.1f} "
                f"${r['gross_pnl']:>11.2f} ${r['total_fees']:>9.2f} "
                f"${r['net_pnl']:>9.2f} {r['net_edge_pct']:>9.2f}%"
            )
    else:
        print("  No combinations met the min edge threshold.")

    # ─── Top 10 by net profit ─────────────────────────────────────────────────
    top10 = sorted(results, key=lambda x: x["net_pnl"], reverse=True)[:10]

    print(f"\n{'=' * 90}")
    print("TOP 10 MOST PROFITABLE COMBINATIONS (by net P&L)")
    print(f"{'=' * 90}")

    header = (
        f"{'#':>3} {'TP':>5} {'SL':>5} {'WR':>6} {'TPD':>5} "
        f"{'Status':>8} {'Net P&L':>10} {'Net Edge%':>10}"
    )
    print(header)
    print("-" * 55)
    for i, r in enumerate(top10, 1):
        status = "PASS" if r["pass_fail"] else "FAIL"
        print(
            f"{i:>3} {r['take_profit_pct']:>5.1f} {r['stop_loss_pct']:>5.1f} "
            f"{r['win_rate']:>6.2f} {r['trades_per_day']:>5.1f} "
            f"{status:>8} ${r['net_pnl']:>9.2f} {r['net_edge_pct']:>9.2f}%"
        )

    # ─── Fee drag breakeven win rates ─────────────────────────────────────────
    print(f"\n{'=' * 90}")
    print("FEE DRAG BREAKEVEN: Minimum win rate (%) needed for net profitability")
    print(f"  (per TP/SL/trades_per_day combo; lower is better for achievable profitability)")
    print(f"{'=' * 90}")

    breakeven_rows = []
    for tp, sl, tpd in itertools.product(take_profit_vals, stop_loss_vals, trades_per_day_vals):
        wr_breakeven = find_fee_breakeven_win_rate(tp, sl, tpd, spread_pct, slippage_pct)
        breakeven_rows.append({
            "take_profit_pct": tp,
            "stop_loss_pct": sl,
            "trades_per_day": tpd,
            "breakeven_win_rate_pct": wr_breakeven,
        })

    # Print as table
    print(f"\n  TPD: trades per day\n")
    tpd_labels = sorted({r["trades_per_day"] for r in breakeven_rows})

    # Build grid: rows = TP, columns = SL, values formatted as TP/SL/WR thresholds
    print(f"  {'TP':>5}  {'':>5}", end="")
    for sl in stop_loss_vals:
        print(f" {'SL='+str(sl):>10}", end="")
    print()
    print(f"  {'':>5}  {'':>5}", end="")
    for _ in stop_loss_vals:
        print(f" {'WR% needed':>10}", end="")
    print()
    print("  " + "-" * (13 + 11 * len(stop_loss_vals)))

    for tp in take_profit_vals:
        print(f"  TP={tp:>2.1f}%", end="")
        for sl in stop_loss_vals:
            wr_breakeven = find_fee_breakeven_win_rate(tp, sl, tpd, spread_pct, slippage_pct)
            print(f"  {wr_breakeven:>9.2f}%", end="")
        print()

    print(f"\n  Note: breakeven WR is per-trade. Targets > 50% for positive expectancy.")
    print(f"  Friction reduces edge for tighter (small TP, small SL) strategies most.\n")

    # ─── Save results as JSON ─────────────────────────────────────────────────
    output_dir = os.path.join(
        os.path.dirname(__file__), "..", "..", "docs", "research"
    )
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "micro_strategy_sweep_results.json")

    output_data = {
        "settings": {
            "capital_usd": CAPITAL_USD,
            "position_size_usd": POSITION_SIZE_FIXED,
            "max_concurrent_positions": MAX_CONCURRENT_POSITIONS,
            "round_trip_fee_pct": ROUND_TRIP_FEE_PCT,
            "spread_pct": spread_pct,
            "slippage_pct": slippage_pct,
            "min_edge_pct": MIN_EDGE_PCT,
            "simulation_days": SIMULATION_DAYS,
            "strategy_type": "SPOT_LONG_ONLY",
        },
        "parameter_ranges": {
            "take_profit_pct": take_profit_vals,
            "stop_loss_pct": stop_loss_vals,
            "win_rate": win_rate_vals,
            "position_size_usd": position_size_vals,
            "trades_per_day": trades_per_day_vals,
        },
        "summary": {
            "total_combinations": total_combos,
            "passing_combinations": len(passing),
            "failing_combinations": len(failing),
            "pass_rate_pct": round(len(passing) / total_combos * 100, 2) if total_combos else 0,
        },
        "passing_results": sorted(passing, key=lambda x: x["net_pnl"], reverse=True),
        "top_10_results": top10,
        "fee_breakeven_win_rates": breakeven_rows,
        "all_results": sorted(results, key=lambda x: x["net_pnl"], reverse=True),
    }

    with open(output_path, "w") as fh:
        json.dump(output_data, fh, indent=2)

    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()
