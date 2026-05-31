"""Paper Trade Ledger — Persistent tracking of simulated trades with live data.

Records every paper trade from entry to exit, stores to JSON, and provides
real-time statistics for edge validation.

This is the PROOF layer: before any real money goes to work, the ledger must
demonstrate a positive edge.

Usage:
    ledger = PaperTradeLedger()
    trade_id = ledger.open_trade(
        pair="BTC/USDT",
        direction="long",
        entry_price=67500.0,
        position_size=0.001,
        stop_loss=64125.0,
        take_profit=74250.0,
        signal_strength=0.65,
        regime="TRENDING_UP",
        intelligence_confidence=0.85,
    )
    # ... later ...
    ledger.close_trade(trade_id, exit_price=71000.0, exit_reason="take_profit")
    stats = ledger.get_statistics()
    report = ledger.generate_report()
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PaperTradeLedger:
    """Persistent paper trade ledger with edge statistics."""

    def __init__(self, filepath: str = "paper_trades_ledger.json", initial_balance: float = 10000.0):
        self.filepath = filepath
        self.initial_balance = initial_balance
        self.trades: List[Dict[str, Any]] = []
        self._next_id: int = 1
        self._load()

    def _load(self) -> None:
        """Load existing ledger from disk."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    data = json.load(f)
                self.trades = data.get("trades", [])
                self._next_id = data.get("next_id", len(self.trades) + 1)
                logger.info(
                    f"[LEDGER] Loaded {len(self.trades)} trades from {self.filepath}"
                )
            except Exception as e:
                logger.warning(f"[LEDGER] Failed to load: {e}, starting fresh")
                self.trades = []
                self._next_id = 1

    def _save(self) -> None:
        """Persist ledger to disk."""
        try:
            data = {"trades": self.trades, "next_id": self._next_id}
            tmp_path = self.filepath + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(tmp_path, self.filepath)
        except Exception as e:
            logger.error(f"[LEDGER] Failed to save: {e}")

    def open_trade(
        self,
        pair: str,
        direction: str,
        entry_price: float,
        position_size: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        signal_strength: float = 0.0,
        regime: str = "",
        intelligence_confidence: float = 0.0,
        intelligence_action: str = "",
        backtest_win_rate: float = 0.0,
        backtest_data_source: str = "",
        metadata: Optional[Dict] = None,
    ) -> int:
        """Open a new paper trade. Returns trade_id."""
        trade_id = self._next_id
        self._next_id += 1

        trade = {
            "trade_id": trade_id,
            "pair": pair,
            "direction": direction,
            "entry_price": entry_price,
            "position_size": position_size,
            "entry_value_usd": entry_price * position_size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_time": datetime.now(timezone.utc).isoformat(),
            "entry_timestamp": time.time(),
            "status": "OPEN",
            "paper_trading": True,
            # Signal context at entry
            "signal_strength": signal_strength,
            "regime_at_entry": regime,
            "intelligence_confidence": intelligence_confidence,
            "intelligence_action": intelligence_action,
            "backtest_win_rate": backtest_win_rate,
            "backtest_data_source": backtest_data_source,
            # Exit fields (filled on close)
            "exit_price": None,
            "exit_time": None,
            "exit_reason": None,
            "pnl_usd": 0.0,
            "pnl_pct": 0.0,
            "fees_usd": 0.0,
            "net_pnl_usd": 0.0,
            "hold_duration_seconds": 0,
            # Extra metadata
            "metadata": metadata or {},
        }

        self.trades.append(trade)
        self._save()
        logger.info(
            f"[LEDGER] Trade #{trade_id} OPENED: {direction} {pair} "
            f"@ {entry_price:.4f} | Size: {position_size:.6f} | "
            f"SL: {stop_loss:.4f} | TP: {take_profit:.4f} | "
            f"Signal: {signal_strength:.3f}"
        )
        return trade_id

    def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        exit_reason: str = "manual",
        fees_pct: float = 0.001,
    ) -> Optional[Dict]:
        """Close an open paper trade. Returns the updated trade dict."""
        trade = self._find_trade(trade_id)
        if trade is None:
            logger.warning(f"[LEDGER] Trade #{trade_id} not found")
            return None
        if trade["status"] != "OPEN":
            logger.warning(f"[LEDGER] Trade #{trade_id} already {trade['status']}")
            return None

        entry_price = trade["entry_price"]
        position_size = trade["position_size"]
        direction = trade["direction"]

        # P&L calculation
        if direction == "long":
            gross_pnl = (exit_price - entry_price) * position_size
        else:  # short
            gross_pnl = (entry_price - exit_price) * position_size

        entry_value = entry_price * position_size
        exit_value = exit_price * position_size
        fees = (entry_value + exit_value) * (fees_pct / 2)  # Round-trip fees

        pnl_pct = (
            (exit_price - entry_price) / entry_price
            if direction == "long"
            else (entry_price - exit_price) / entry_price
        )

        now = datetime.now(timezone.utc)
        hold_duration = time.time() - trade.get("entry_timestamp", time.time())

        trade.update(
            {
                "exit_price": exit_price,
                "exit_time": now.isoformat(),
                "exit_reason": exit_reason,
                "pnl_usd": gross_pnl,
                "pnl_pct": pnl_pct,
                "fees_usd": fees,
                "net_pnl_usd": gross_pnl - fees,
                "hold_duration_seconds": hold_duration,
                "status": "CLOSED",
            }
        )
        self._save()

        result_emoji = "WIN" if trade["net_pnl_usd"] > 0 else "LOSS"
        logger.info(
            f"[LEDGER] Trade #{trade_id} CLOSED: {result_emoji} | "
            f"{trade['pair']} {trade['direction']} | "
            f"P&L: ${trade['net_pnl_usd']:.4f} ({pnl_pct:+.2%}) | "
            f"Reason: {exit_reason} | Hold: {hold_duration/3600:.1f}h"
        )
        return trade

    def monitor_open_positions(self, current_prices: Dict[str, float]) -> List[Dict]:
        """Check all open positions against current prices.

        Auto-close if stop_loss or take_profit hit.
        Returns list of closed trades.
        """
        closed = []
        for trade in self.trades:
            if trade["status"] != "OPEN":
                continue

            pair = trade["pair"]
            if pair not in current_prices:
                continue

            current_price = current_prices[pair]
            stop_loss = trade["stop_loss"]
            take_profit = trade["take_profit"]
            direction = trade["direction"]

            should_close = False
            reason = ""

            if direction == "long":
                if stop_loss > 0 and current_price <= stop_loss:
                    should_close = True
                    reason = "stop_loss"
                elif take_profit > 0 and current_price >= take_profit:
                    should_close = True
                    reason = "take_profit"
            elif direction == "short":
                if stop_loss > 0 and current_price >= stop_loss:
                    should_close = True
                    reason = "stop_loss"
                elif take_profit > 0 and current_price <= take_profit:
                    should_close = True
                    reason = "take_profit"

            if should_close:
                result = self.close_trade(trade["trade_id"], current_price, reason)
                if result:
                    closed.append(result)

        return closed

    def force_close_all(
        self, current_prices: Dict[str, float], reason: str = "force_close"
    ) -> List[Dict]:
        """Force-close all open positions at current market prices."""
        closed = []
        for trade in self.trades:
            if trade["status"] != "OPEN":
                continue
            pair = trade["pair"]
            price = current_prices.get(pair, trade["entry_price"])
            result = self.close_trade(trade["trade_id"], price, reason)
            if result:
                closed.append(result)
        return closed

    def get_open_trades(self) -> List[Dict]:
        """Return all open trades."""
        return [t for t in self.trades if t["status"] == "OPEN"]

    def get_closed_trades(self) -> List[Dict]:
        """Return all closed trades."""
        return [t for t in self.trades if t["status"] == "CLOSED"]

    def get_statistics(self) -> Dict[str, Any]:
        """Compute edge validation statistics from closed trades."""
        closed = self.get_closed_trades()
        if not closed:
            return {
                "total_trades": 0,
                "open_trades": len(self.get_open_trades()),
                "win_rate": 0.0,
                "total_pnl_usd": 0.0,
                "total_pnl_pct": 0.0,
                "avg_win_pct": 0.0,
                "avg_loss_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "profit_factor": 0.0,
                "sharpe_approx": 0.0,
                "avg_hold_hours": 0.0,
                "edge_proven": False,
                "edge_required_trades": 30,
            }

        pnls = [t["pnl_pct"] for t in closed]
        net_pnls = [t["net_pnl_usd"] for t in closed]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_wins_usd = sum(
            t["net_pnl_usd"] for t in closed if t["net_pnl_usd"] > 0
        )
        total_losses_usd = abs(
            sum(t["net_pnl_usd"] for t in closed if t["net_pnl_usd"] <= 0)
        )

        # Max drawdown from equity curve (relative to account balance, not just P&L)
        equity = self.initial_balance
        peak = self.initial_balance
        max_dd = 0.0
        for pnl in net_pnls:
            equity += pnl
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd

        # Sharpe approximation (annualized)
        import numpy as np

        if len(pnls) > 1:
            sharpe = (
                float(np.mean(pnls) / np.std(pnls)) * (8760**0.5)
                if np.std(pnls) > 0
                else 0.0
            )
        else:
            sharpe = 0.0

        # Average hold duration
        hold_hours = [
            t.get("hold_duration_seconds", 0) / 3600 for t in closed
        ]

        # Per-pair breakdown
        pair_stats = {}
        for t in closed:
            pair = t["pair"]
            if pair not in pair_stats:
                pair_stats[pair] = {"trades": 0, "wins": 0, "pnl": 0.0}
            pair_stats[pair]["trades"] += 1
            if t["net_pnl_usd"] > 0:
                pair_stats[pair]["wins"] += 1
            pair_stats[pair]["pnl"] += t["net_pnl_usd"]

        for pair in pair_stats:
            ps = pair_stats[pair]
            ps["win_rate"] = ps["wins"] / ps["trades"] if ps["trades"] > 0 else 0

        # Edge proof: need 30+ trades AND positive expectancy AND Sharpe > 0.5
        min_trades = 30
        has_enough_trades = len(closed) >= min_trades
        has_positive_expectancy = (np.mean(pnls) > 0) if pnls else False
        has_good_sharpe = sharpe > 0.5
        edge_proven = has_enough_trades and has_positive_expectancy and has_good_sharpe

        return {
            "total_trades": len(closed),
            "open_trades": len(self.get_open_trades()),
            "win_rate": len(wins) / len(closed) if closed else 0,
            "total_pnl_usd": sum(net_pnls),
            "total_pnl_pct": sum(pnls),
            "avg_win_pct": float(np.mean(wins)) if wins else 0.0,
            "avg_loss_pct": float(np.mean(losses)) if losses else 0.0,
            "max_drawdown_pct": max_dd,
            "profit_factor": (
                total_wins_usd / total_losses_usd
                if total_losses_usd > 0
                else float("inf")
            ),
            "sharpe_approx": round(sharpe, 2),
            "avg_hold_hours": float(np.mean(hold_hours)) if hold_hours else 0.0,
            "pair_breakdown": pair_stats,
            "edge_proven": edge_proven,
            "edge_details": {
                "has_enough_trades": has_enough_trades,
                "trades_needed": max(0, min_trades - len(closed)),
                "has_positive_expectancy": has_positive_expectancy,
                "expectancy_per_trade": float(np.mean(pnls)) if pnls else 0.0,
                "has_good_sharpe": has_good_sharpe,
                "sharpe_required": 0.5,
            },
        }

    def generate_report(self) -> str:
        """Generate a human-readable edge validation report."""
        stats = self.get_statistics()
        closed = self.get_closed_trades()

        lines = [
            "=" * 70,
            "  PAPER TRADE EDGE VALIDATION REPORT",
            f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "=" * 70,
            "",
            "SUMMARY",
            "-" * 40,
            f"  Total trades:      {stats['total_trades']}",
            f"  Open positions:    {stats['open_trades']}",
            f"  Win rate:          {stats['win_rate']:.1%}",
            f"  Total P&L:         ${stats['total_pnl_usd']:.4f}",
            f"  Cumulative return: {stats['total_pnl_pct']:+.2%}",
            f"  Avg win:           +{stats['avg_win_pct']:.2%}",
            f"  Avg loss:          {stats['avg_loss_pct']:.2%}",
            f"  Max drawdown:      {stats['max_drawdown_pct']:.1%}",
            f"  Profit factor:     {stats['profit_factor']:.2f}",
            f"  Sharpe (approx):   {stats['sharpe_approx']:.2f}",
            f"  Avg hold time:     {stats['avg_hold_hours']:.1f}h",
            "",
            "EDGE VALIDATION",
            "-" * 40,
        ]

        details = stats.get("edge_details", {})
        if stats["edge_proven"]:
            lines.append(
                "  *** EDGE PROVEN — Strategy demonstrates positive expectancy ***"
            )
        else:
            lines.append("  EDGE NOT YET PROVEN")
            if not details.get("has_enough_trades"):
                lines.append(
                    f"  - Need {details.get('trades_needed', 30)} more trades (minimum 30)"
                )
            if not details.get("has_positive_expectancy"):
                lines.append(
                    f"  - Expectancy is negative: {details.get('expectancy_per_trade', 0):.4f}"
                )
            if not details.get("has_good_sharpe"):
                lines.append(
                    f"  - Sharpe too low: {stats['sharpe_approx']:.2f} < 0.5"
                )

        lines.append("")

        if stats.get("pair_breakdown"):
            lines.append("PER-PAIR BREAKDOWN")
            lines.append("-" * 40)
            for pair, ps in sorted(stats["pair_breakdown"].items()):
                lines.append(
                    f"  {pair:12s} | {ps['trades']} trades | "
                    f"WR: {ps['win_rate']:.1%} | P&L: ${ps['pnl']:.4f}"
                )

        if closed:
            lines.append("")
            lines.append("RECENT TRADES (last 10)")
            lines.append("-" * 70)
            for t in closed[-10:]:
                result = "WIN " if t["net_pnl_usd"] > 0 else "LOSS"
                lines.append(
                    f"  #{t['trade_id']:3d} | {t['pair']:10s} | {t['direction']:5s} | "
                    f"Entry: {t['entry_price']:.4f} | Exit: {t.get('exit_price', 0):.4f} | "
                    f"P&L: ${t['net_pnl_usd']:+.4f} | {t.get('exit_reason', '?'):15s} | {result}"
                )

        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)

    def _find_trade(self, trade_id: int) -> Optional[Dict]:
        """Find a trade by ID."""
        for trade in self.trades:
            if trade["trade_id"] == trade_id:
                return trade
        return None

    def reset(self) -> None:
        """Clear all trades (for fresh simulation)."""
        self.trades = []
        self._next_id = 1
        self._save()
        logger.info("[LEDGER] Reset — all trades cleared")
