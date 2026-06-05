#!/usr/bin/env python3
"""
Real-data BTC/USDT compounding parameter sweep.

Replays bar-by-bar on 120d of KuCoin 1h klines using a simplified but realistic
clone of the live exit stack:
SL -> breakeven move -> trailing -> R:R take-profit -> SELL signal
with MIN_PROFIT_TO_HOLD_PCT gate

Single-position, spot-long-only, compounding equity, taker fees on both sides.

Outputs:
docs/research/btc_compounding_sweep_results.json (every combo)
docs/research/TESTING_RESULTS.md (top 30 + narrative)

Designed to be FAST: indicators are pre-computed once per (ema_fast, ema_slow,
rsi_period) tuple, then the parameter grid iterates over the cached series.

Usage:
python3 scripts/research/run_btc_compounding_sweep.py
python3 scripts/research/run_btc_compounding_sweep.py --top 50 --start-equity 110
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import os
import sys
import time
from dataclasses import dataclass, asdict
from itertools import product
from pathlib import Path
from typing import Iterable

import numpy as np


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
def load_csv(path: Path) -> dict[str, np.ndarray]:
    rows = list(csv.DictReader(path.open()))
    return {
        "ts": np.array([int(r["ts"]) for r in rows], dtype=np.int64),
        "open": np.array([float(r["open"]) for r in rows]),
        "high": np.array([float(r["high"]) for r in rows]),
        "low": np.array([float(r["low"]) for r in rows]),
        "close": np.array([float(r["close"]) for r in rows]),
        "volume": np.array([float(r["volume"]) for r in rows]),
    }


# --------------------------------------------------------------------------- #
# Indicators (numpy)
# --------------------------------------------------------------------------- #
def ema(arr: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1)
    out = np.empty_like(arr)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def wilder_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.empty_like(close)
    avg_loss = np.empty_like(close)
    avg_gain[:period] = gain[:period].mean()
    avg_loss[:period] = loss[:period].mean()
    for i in range(period, len(close)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period
    rs = np.where(avg_loss == 0, 0.0, avg_gain / np.maximum(avg_loss, 1e-12))
    rsi = np.where(avg_loss == 0, 100.0, 100.0 - (100.0 / (1.0 + rs)))
    return rsi


# --------------------------------------------------------------------------- #
# Signal: RSI-oversold long entry with EMA trend filter
# BUY = rsi crosses up through rsi_buy_threshold AND close > ema_slow
# SELL = rsi crosses down through rsi_sell_threshold (e.g. 70)
# --------------------------------------------------------------------------- #
def build_signals(
    close: np.ndarray,
    rsi: np.ndarray,
    ema_slow: np.ndarray,
    rsi_buy: float,
    rsi_sell: float,
    require_trend: bool,
) -> tuple[np.ndarray, np.ndarray]:
    rsi_prev = np.concatenate([[rsi[0]], rsi[:-1]])
    buy = (rsi_prev < rsi_buy) & (rsi >= rsi_buy)
    if require_trend:
        buy = buy & (close > ema_slow)
    sell = (rsi_prev > rsi_sell) & (rsi <= rsi_sell)
    return buy, sell


# --------------------------------------------------------------------------- #
# Backtest engine
# --------------------------------------------------------------------------- #
@dataclass
class Result:
    # parameters
    risk_pct: float
    stop_loss_pct: float
    rr: float
    rsi_buy: float
    rsi_sell: float
    ema_fast: int
    ema_slow: int
    rsi_period: int
    trail_activate_pct: float
    trail_pct: float
    breakeven_activate_pct: float
    require_trend: bool
    min_profit_hold_pct: float
    # outcomes
    trades: int
    wins: int
    win_rate: float
    final_equity: float
    net_return_pct: float
    max_drawdown_pct: float
    profit_factor: float
    avg_win_pct: float
    avg_loss_pct: float
    sharpe_like: float
    days: float


def simulate(
    bars: dict[str, np.ndarray],
    buy: np.ndarray,
    sell: np.ndarray,
    start_equity: float,
    risk_pct: float,
    stop_loss_pct: float,
    rr: float,
    trail_activate_pct: float,
    trail_pct: float,
    breakeven_activate_pct: float,
    min_profit_hold_pct: float,
    fee_pct: float,
    micro_account_threshold: float,
    confidence_floor: float,
    asset_multiplier: float,
    min_notional: float,
    warmup: int,
) -> tuple[list[float], list[float], list[bool], float]:
    """Returns (trade_returns_pct, equity_curve, win_flags, peak_dd_pct)."""
    high = bars["high"]
    low = bars["low"]
    close = bars["close"]
    n = len(close)

    equity = start_equity
    peak_equity = start_equity
    max_dd = 0.0
    equity_curve = [equity]
    trade_returns: list[float] = []
    win_flags: list[bool] = []

    # position state
    in_pos = False
    entry_price = 0.0
    qty = 0.0
    stop = 0.0
    take = 0.0
    trail_armed = False
    breakeven_done = False
    peak_in_trade = 0.0

    for i in range(warmup, n):
        h, l, c = high[i], low[i], close[i]

        if in_pos:
            peak_in_trade = max(peak_in_trade, h)

            # breakeven move
            if not breakeven_done:
                if (peak_in_trade / entry_price - 1.0) * 100.0 >= breakeven_activate_pct:
                    stop = max(stop, entry_price * (1.0 + fee_pct * 2))
                    breakeven_done = True

            # trailing arm + ratchet
            if not trail_armed:
                if (peak_in_trade / entry_price - 1.0) * 100.0 >= trail_activate_pct:
                    trail_armed = True
            if trail_armed:
                new_stop = peak_in_trade * (1.0 - trail_pct / 100.0)
                stop = max(stop, new_stop)

            # exit checks in priority order
            exit_price = None
            exit_reason = ""

            # adverse first (stop checked before TP in same bar)
            if l <= stop:
                exit_price = stop
                exit_reason = "stop"
            elif h >= take:
                exit_price = take
                exit_reason = "tp"
            elif sell[i]:
                cur_profit_pct = (c / entry_price - 1.0) * 100.0
                if cur_profit_pct < min_profit_hold_pct:
                    exit_price = c
                    exit_reason = "sell_signal"

            if exit_price is not None:
                gross_ret = (exit_price - entry_price) / entry_price
                net_ret = gross_ret - 2 * fee_pct
                pnl = qty * entry_price * net_ret
                equity += pnl
                trade_returns.append(net_ret * 100.0)
                win_flags.append(net_ret > 0)
                in_pos = False
                qty = 0.0
                trail_armed = False
                breakeven_done = False
                peak_in_trade = 0.0
                peak_equity = max(peak_equity, equity)
                dd = (peak_equity - equity) / peak_equity * 100.0
                max_dd = max(max_dd, dd)

            equity_curve.append(equity)

        # new entry (only when flat, no entry on same bar as exit)
        if not in_pos and buy[i]:
            max_risk_amount = equity * risk_pct
            if equity < micro_account_threshold:
                cm = 1.0
            else:
                cm = max(0.5, confidence_floor)
            risk_dollars = max_risk_amount * cm
            risk_per_unit = c * (stop_loss_pct / 100.0)
            if risk_per_unit <= 0:
                continue
            raw_qty = risk_dollars / risk_per_unit
            qty_attempt = raw_qty * asset_multiplier
            notional = qty_attempt * c
            if notional < min_notional:
                continue
            if notional > equity * 0.95:
                qty_attempt = (equity * 0.95) / c

            in_pos = True
            entry_price = c
            qty = qty_attempt
            stop = entry_price * (1.0 - stop_loss_pct / 100.0)
            take = entry_price * (1.0 + (stop_loss_pct * rr) / 100.0)
            peak_in_trade = entry_price

    # close any open position at last close
    if in_pos:
        gross_ret = (close[-1] - entry_price) / entry_price
        net_ret = gross_ret - 2 * fee_pct
        pnl = qty * entry_price * net_ret
        equity += pnl
        trade_returns.append(net_ret * 100.0)
        win_flags.append(net_ret > 0)
        equity_curve[-1] = equity
        peak_equity = max(peak_equity, equity)
        dd = (peak_equity - equity) / peak_equity * 100.0
        max_dd = max(max_dd, dd)

    return trade_returns, equity_curve, win_flags, max_dd


# --------------------------------------------------------------------------- #
# Grid sweep
# --------------------------------------------------------------------------- #
def grid() -> Iterable[dict]:
    risk_pcts = [0.0075, 0.010, 0.015, 0.020]
    stop_loss_pcts = [1.0, 1.5, 2.0, 2.5, 3.0]
    rrs = [1.5, 2.0, 2.5, 3.0]
    rsi_buys = [25, 30, 35, 40]
    rsi_sells = [65, 70, 75]
    ema_pairs = [(9, 50), (9, 100), (21, 50), (21, 100)]
    rsi_periods = [14]
    trail_activates = [1.5, 2.0, 3.0]
    trail_pcts = [1.5]
    breakeven_acts = [1.0]
    require_trends = [True, False]
    min_profit_holds = [1.0]
    # total = 4*5*4*4*3*4*1*3*1*1*2*1 = 23,040
    for (rp, sl, rr_, rb, rs_, (ef, es), rsip, ta, tp, ba, rt, mph) in product(
        risk_pcts, stop_loss_pcts, rrs, rsi_buys, rsi_sells,
        ema_pairs, rsi_periods, trail_activates, trail_pcts,
        breakeven_acts, require_trends, min_profit_holds,
    ):
        yield {
            "risk_pct": rp, "stop_loss_pct": sl, "rr": rr_,
            "rsi_buy": rb, "rsi_sell": rs_,
            "ema_fast": ef, "ema_slow": es, "rsi_period": rsip,
            "trail_activate_pct": ta, "trail_pct": tp,
            "breakeven_activate_pct": ba, "require_trend": rt,
            "min_profit_hold_pct": mph,
        }


def run(args: argparse.Namespace) -> None:
    csv_path = Path(args.data)
    if not csv_path.exists():
        print(f"ERROR: data file not found: {csv_path}")
        print("Run scripts/research/fetch_btc_history.py first.")
        sys.exit(1)

    bars = load_csv(csv_path)
    n = len(bars["close"])
    days = (bars["ts"][-1] - bars["ts"][0]) / 86400
    print(f"Loaded {n} bars ({days:.1f} days)")

    indicator_cache: dict[tuple, dict] = {}
    print("Pre-computing indicators...")
    for ef, es in [(9, 50), (9, 100), (21, 50), (21, 100)]:
        for rsip in [14]:
            key = (ef, es, rsip)
            indicator_cache[key] = {
                "ema_fast": ema(bars["close"], ef),
                "ema_slow": ema(bars["close"], es),
                "rsi": wilder_rsi(bars["close"], rsip),
            }
    print(f" cached {len(indicator_cache)} indicator sets")

    combos = list(grid())
    print(f"Running sweep: {len(combos):,} combos...")

    results: list[Result] = []
    t0 = time.time()
    last_print = t0
    for idx, p in enumerate(combos):
        ind = indicator_cache[(p["ema_fast"], p["ema_slow"], p["rsi_period"])]
        buy, sell = build_signals(
            bars["close"], ind["rsi"], ind["ema_slow"],
            p["rsi_buy"], p["rsi_sell"], p["require_trend"],
        )
        warmup = max(p["ema_slow"], p["rsi_period"]) + 1
        rets, eq_curve, wins, mdd = simulate(
            bars, buy, sell,
            start_equity=args.start_equity,
            risk_pct=p["risk_pct"],
            stop_loss_pct=p["stop_loss_pct"],
            rr=p["rr"],
            trail_activate_pct=p["trail_activate_pct"],
            trail_pct=p["trail_pct"],
            breakeven_activate_pct=p["breakeven_activate_pct"],
            min_profit_hold_pct=p["min_profit_hold_pct"],
            fee_pct=args.fee_pct,
            micro_account_threshold=200.0,
            confidence_floor=0.6,
            asset_multiplier=0.80,
            min_notional=5.0,
            warmup=warmup,
        )
        n_trades = len(rets)
        n_wins = sum(wins)
        wr = (n_wins / n_trades) if n_trades else 0.0
        final_eq = eq_curve[-1]
        net_ret = (final_eq / args.start_equity - 1.0) * 100.0
        if rets:
            wins_arr = np.array([r for r in rets if r > 0])
            losses_arr = np.array([r for r in rets if r <= 0])
            gw = wins_arr.sum() if wins_arr.size else 0.0
            gl = -losses_arr.sum() if losses_arr.size else 0.0
            pf = (gw / gl) if gl > 0 else (float("inf") if gw > 0 else 0.0)
            aw = wins_arr.mean() if wins_arr.size else 0.0
            al = losses_arr.mean() if losses_arr.size else 0.0
            mu = float(np.mean(rets))
            sd = float(np.std(rets)) or 1e-9
            sharpe_like = (mu / sd) * math.sqrt(max(n_trades, 1))
        else:
            pf = 0.0; aw = 0.0; al = 0.0; sharpe_like = 0.0

        results.append(Result(
            risk_pct=p["risk_pct"], stop_loss_pct=p["stop_loss_pct"], rr=p["rr"],
            rsi_buy=p["rsi_buy"], rsi_sell=p["rsi_sell"],
            ema_fast=p["ema_fast"], ema_slow=p["ema_slow"],
            rsi_period=p["rsi_period"],
            trail_activate_pct=p["trail_activate_pct"], trail_pct=p["trail_pct"],
            breakeven_activate_pct=p["breakeven_activate_pct"],
            require_trend=p["require_trend"],
            min_profit_hold_pct=p["min_profit_hold_pct"],
            trades=n_trades, wins=n_wins, win_rate=wr,
            final_equity=final_eq, net_return_pct=net_ret,
            max_drawdown_pct=mdd, profit_factor=pf if math.isfinite(pf) else 999.0,
            avg_win_pct=aw, avg_loss_pct=al, sharpe_like=sharpe_like,
            days=days,
        ))

        if time.time() - last_print > 3:
            done = idx + 1
            elapsed = time.time() - t0
            rate = done / elapsed
            eta = (len(combos) - done) / rate
            print(f" {done:,}/{len(combos):,} ({rate:.0f}/s) ETA {eta:.0f}s")
            last_print = time.time()

    elapsed = time.time() - t0
    print(f"Done. {len(results):,} combos in {elapsed:.1f}s ({len(results)/elapsed:.0f}/s)")

    # ---- save raw results ----
    out_json = Path("docs/research/btc_compounding_sweep_results.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    def _scrub(v):
        if isinstance(v, np.generic):
            v = v.item()
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                return None
        return v
    payload = {
        "data_file": str(csv_path),
        "bars": n,
        "days": days,
        "start_equity": args.start_equity,
        "fee_pct": args.fee_pct,
        "n_combos": len(results),
        "results": [{k: _scrub(v) for k, v in asdict(r).items()} for r in results],
    }
    with out_json.open("w") as f:
        json.dump(payload, f)
    print(f" raw -> {out_json}")

    # ---- rank + report ----
    min_trades = 8
    qualified = [r for r in results if r.trades >= min_trades]
    print(f" qualified (>={min_trades} trades): {len(qualified)}/{len(results)}")

    qualified.sort(key=lambda r: r.net_return_pct - 0.5 * r.max_drawdown_pct, reverse=True)
    top = qualified[: args.top]
    write_results_md(top, results, qualified, days, args)


def write_results_md(top, all_results, qualified, days, args) -> None:
    out_md = Path("docs/research/TESTING_RESULTS.md")
    out_md.parent.mkdir(parents=True, exist_ok=True)

    n_profit = sum(1 for r in qualified if r.net_return_pct > 0)
    pct_profit = (n_profit / len(qualified) * 100) if qualified else 0.0

    lines = []
    lines.append("# BTC/USDT Compounding Parameter Sweep -- Results (REAL DATA)")
    lines.append("")
    lines.append(f"- **Data**: `{args.data}` ({days:.1f} days of real KuCoin 1h candles)")
    lines.append(f"- **Start equity**: ${args.start_equity:.2f}")
    lines.append(f"- **Fee per side**: {args.fee_pct*100:.2f}%")
    lines.append(f"- **Total combos tested**: {len(all_results):,}")
    lines.append(f"- **Qualified (>=8 trades)**: {len(qualified):,}")
    lines.append(f"- **Profitable (net > 0)**: {n_profit:,} ({pct_profit:.1f}%)")
    lines.append("")
    lines.append("## Ranking method")
    lines.append("`score = net_return_pct - 0.5 * max_drawdown_pct`")
    lines.append("")
    lines.append("Filtered to combos with >=8 trades to avoid lucky 1-trade flukes.")
    lines.append("")
    lines.append(f"## Top {len(top)} configurations")
    lines.append("")
    lines.append(
        "| # | Risk% | SL% | R:R | RSI buy/sell | EMA f/s | Trail act/% | BE act% | Trend? | Hold% "
        "| Trades | WR | Net% | MaxDD% | PF | Score |"
    )
    lines.append(
        "|---|------:|----:|----:|--------------|---------|-------------|--------:|--------|------:"
        "|-------:|---:|-----:|-------:|---:|------:|"
    )
    for i, r in enumerate(top, 1):
        score = r.net_return_pct - 0.5 * r.max_drawdown_pct
        lines.append(
            f"| {i} | {r.risk_pct*100:.2f} | {r.stop_loss_pct:.1f} | {r.rr:.1f} "
            f"| {r.rsi_buy:.0f}/{r.rsi_sell:.0f} "
            f"| {r.ema_fast}/{r.ema_slow} "
            f"| {r.trail_activate_pct:.1f}/{r.trail_pct:.1f} "
            f"| {r.breakeven_activate_pct:.1f} "
            f"| {'Y' if r.require_trend else 'N'} "
            f"| {r.min_profit_hold_pct:.1f} "
            f"| {r.trades} | {r.win_rate*100:.0f}% "
            f"| {r.net_return_pct:+.1f} | {r.max_drawdown_pct:.1f} "
            f"| {r.profit_factor:.2f} | {score:+.1f} |"
        )

    if top:
        b = top[0]
        lines.append("")
        lines.append("## #1 configuration -- recommended starting params")
        lines.append("")
        lines.append("```")
        lines.append(f"RISK_PER_TRADE = {b.risk_pct}")
        lines.append(f"DEFAULT_STOP_LOSS_PCT = {b.stop_loss_pct/100}")
        lines.append(f"MIN_RISK_REWARD_RATIO = {b.rr}")
        lines.append(f"RSI_BUY_THRESHOLD = {b.rsi_buy}")
        lines.append(f"RSI_SELL_THRESHOLD = {b.rsi_sell}")
        lines.append(f"EMA_FAST = {b.ema_fast}")
        lines.append(f"EMA_SLOW = {b.ema_slow}")
        lines.append(f"RSI_PERIOD = {b.rsi_period}")
        lines.append(f"TRAILING_ACTIVATION_PCT = {b.trail_activate_pct}")
        lines.append(f"TRAILING_PCT = {b.trail_pct}")
        lines.append(f"BREAKEVEN_ACTIVATION_PCT = {b.breakeven_activate_pct}")
        lines.append(f"REQUIRE_TREND_FILTER = {b.require_trend}")
        lines.append(f"MIN_PROFIT_TO_HOLD_PCT = {b.min_profit_hold_pct}")
        lines.append("")
        lines.append(f"# Backtest on real KuCoin 1h data:")
        lines.append(f"# trades = {b.trades}")
        lines.append(f"# win rate = {b.win_rate*100:.1f}%")
        lines.append(f"# net return = {b.net_return_pct:+.2f}%")
        lines.append(f"# max drawdown = {b.max_drawdown_pct:.2f}%")
        lines.append(f"# profit factor = {b.profit_factor:.2f}")
        lines.append(f"# avg win = {b.avg_win_pct:+.2f}%")
        lines.append(f"# avg loss = {b.avg_loss_pct:+.2f}%")
        lines.append(f"# final equity = ${b.final_equity:.2f} (from ${args.start_equity:.2f})")
        lines.append("```")

    if qualified:
        lines.append("")
        lines.append("## Parameter influence (top 10% of qualified)")
        lines.append("")
        top_decile_n = max(1, len(qualified) // 10)
        top_decile = qualified[:top_decile_n]
        from collections import Counter
        def freq(attr):
            c = Counter(getattr(r, attr) for r in top_decile)
            tot = sum(c.values())
            return ", ".join(f"`{k}`: {v/tot*100:.0f}%" for k, v in sorted(c.items(), key=lambda x: -x[1]))
        for attr, label in [
            ("risk_pct", "Risk per trade"),
            ("stop_loss_pct", "Stop loss %"),
            ("rr", "R:R"),
            ("rsi_buy", "RSI buy"),
            ("rsi_sell", "RSI sell"),
            ("ema_fast", "EMA fast"),
            ("ema_slow", "EMA slow"),
            ("trail_activate_pct", "Trail activate %"),
            ("require_trend", "Trend filter"),
        ]:
            lines.append(f"- **{label}**: {freq(attr)}")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_Generated by `scripts/research/run_btc_compounding_sweep.py`._")
    lines.append("_Strategy: RSI-oversold long entry with optional EMA trend filter; exit stack: SL -> breakeven -> trailing -> R:R TP -> SELL signal (gated by MIN_PROFIT_TO_HOLD_PCT)._")
    lines.append("_Spot-long-only, single position, 0.1% taker fee each side, compounding equity._")
    lines.append("_IMPORTANT: This uses REAL KuCoin OHLCV data, not synthetic simulation._")
    lines.append("")

    out_md.write_text("\n".join(lines))
    print(f" report -> {out_md}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/btc_usdt_1h.csv")
    ap.add_argument("--start-equity", type=float, default=110.0)
    ap.add_argument("--fee-pct", type=float, default=0.001)
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()
    run(args)


if __name__ == "__main__":
    main()
