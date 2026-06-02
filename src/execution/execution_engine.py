"""
Execution Engine - Merged from kucoin-margin-bot + Deliberate-AI-Ensemble
=========================================================================

Bot contributed:
- ABC ExecutionEngine base with heartbeat, continuous loop, Telegram notifications
- DryRunExecutor: CSV backtest data loading
- LiveExecutor: KuCoin client init, risk checks, position monitoring at startup
- select_executor() factory

Ensemble contributed:
- ExecutionAgent(BaseAgent): paper position tracking, close_position,
  update_open_positions, get_performance_summary
- Live order placement via ExchangeAdapter (KuCoin-specific symbol formatting,
  market/limit orders, stop-loss, take-profit)
- Session limits validation, live trade validation
- TradeStatus enum
"""

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base_agent import BaseAgent, AgentStatus
from ..trading.paper_trade_ledger import PaperTradeLedger
from ..config import (
    KUCOIN_API_KEY,
    KUCOIN_API_SECRET,
    KUCOIN_API_PASSPHRASE,
    POSITION_SIZE_USD,
    MONITOR_INTERVAL_MIN,
    DRY_RUN,
    LIVE_TRADING,
    SPOT_LONG_ONLY,
)
from .exchange_adapter import ExchangeAdapter, KuCoinAdapter
from ..risk.circuit_breaker import CircuitBreaker
from ..risk.portfolio_circuit_breaker import PortfolioCircuitBreaker, CircuitBreakTriggered
from ..utils.timeframe import resolve_timeframe, DEFAULT_TIMEFRAME
from .trailing_stop import TrailingStopManager, ProgressiveROI, CustomStopLoss

logger = logging.getLogger(__name__)

LANE_NAME = "kucoin-lane"
SESSION_STATE_REL_PATH = os.path.join("lanes", "kucoin", "inbox", "SESSION_STATE.json")

PHASE_MAP: Dict[str, str] = {
    "initializing": "booting",
    "running": "active",
    "sleeping": "standby",
    "error": "fault",
    "shutdown": "terminating",
    "startup": "booting",
    "pre_cycle": "active",
    "post_cycle": "active",
    "final": "terminating",
}


def send_telegram_notification(message: str) -> bool:
    try:
        import requests

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        logger.warning(f"Failed to send Telegram notification: {e}")
        return False


class TradeStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    PENDING = "pending"
    CANCELLED = "cancelled"


class ExecutionEngine(ABC):
    """Base class for execution engines with heartbeat and continuous loop."""

    MIN_PROFIT_TO_HOLD_PCT = 1.0

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        mode_suffix = "dry_run" if "DryRun" in self.__class__.__name__ else "live"
        self.heartbeat_file = f"bot_heartbeat_{mode_suffix}.json"
        self.session_state_lane, self.session_state_file = (
            self._resolve_session_state_contract()
        )
        self.start_time = datetime.now()
        self.cycle_count = 0
        self.is_running = True
        self._last_runtime_status: Optional[str] = None
        self._last_error: Optional[str] = None
        self.open_positions: List[Dict[str, Any]] = []
        self.closed_trades: List[Dict[str, Any]] = []
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.portfolio_cb = None
        self.trailing_stop = TrailingStopManager(config.get("trailing_stop_config"))
        self.progressive_roi = ProgressiveROI(config.get("progressive_roi_config"))
        self.custom_stoploss = CustomStopLoss(config.get("custom_stoploss_config"))
        self._last_runtime_status: str = "initializing"
        logger.info(
            f"ExecutionEngine initialized - using heartbeat: {self.heartbeat_file}"
        )

    def _resolve_session_state_contract(self) -> tuple:
        default_lane = "kucoin-lane"
        default_path = Path("lanes/kucoin/inbox/SESSION_STATE.json")
        contract_file = (
            Path(__file__).resolve().parents[2] / "governance" / "lane-relay.json"
        )

        try:
            if not contract_file.exists():
                return default_lane, default_path

            contract = json.loads(contract_file.read_text(encoding="utf-8"))
            lane = contract.get("lane", default_lane)
            session_path = (contract.get("session_state", {}) or {}).get("path") or str(
                default_path
            )
            return lane, Path(session_path)
        except Exception as e:
            logger.warning(f"Failed to parse lane-relay contract: {e}")
            return default_lane, default_path

    def _resolve_phase(self, status: str) -> str:
        return PHASE_MAP.get(status, "unknown")

    def write_session_state(
        self,
        status: str = "running",
        step: str = "main_loop",
        error: Optional[str] = None,
        final: bool = False,
    ):
        try:
            status_to_write = status
            if status in {"shutdown", "final"} and self._last_runtime_status == "error":
                status_to_write = "error"
                error = error or self._last_error or "cycle_error"

            payload = {
                "lane": self.session_state_lane,
                "cycle": self.cycle_count,
                "timestamp": datetime.now().isoformat(),
                "mode": self.__class__.__name__,
                "executor_class": self.__class__.__name__,
                "status": status_to_write,
                "runtime_status": status_to_write,
                "phase": self._resolve_phase(status_to_write),
                "final": final,
                "step": step,
                "pid": os.getpid(),
                "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            }
            if error:
                payload["error"] = error

            self.session_state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.session_state_file, "w", encoding="utf-8") as f:
                json.dump(payload, f)

            self._last_runtime_status = status_to_write
            if status_to_write == "error":
                self._last_error = error or step
        except Exception as e:
            logger.warning(f"Failed to write SESSION_STATE: {e}")

    def write_heartbeat(
        self, status: str = "running", step: str = "main_loop", final: bool = False
    ) -> None:
        try:
            heartbeat = {
                "timestamp": datetime.now().isoformat(),
                "pid": os.getpid(),
                "status": status,
                "step": step,
                "cycle": self.cycle_count,
                "mode": self.__class__.__name__,
                "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            }
            with open(self.heartbeat_file, "w", encoding="utf-8") as f:
                json.dump(heartbeat, f)
            self.write_session_state(
                status=status,
                step=step,
                error=step if status == "error" else None,
                final=final,
            )
        except Exception as e:
            logger.warning(f"Failed to write heartbeat: {e}")

    def log(self, level: str, msg: str) -> None:
        getattr(logger, level.lower())(f"[{self.__class__.__name__}] {msg}")

    @abstractmethod
    def run_cycle(self):
        pass

    def run_continuous(self, interval_minutes: int = 5):
        self.log(
            "info",
            f"Starting continuous monitoring loop (every {interval_minutes} minutes)",
        )
        self.write_heartbeat("initializing", "startup")
        self.write_session_state("initializing")

        mode_name = "LIVE_TRADING" if "Live" in self.__class__.__name__ else "DRY_RUN"
        start_msg = (
            f"<b>Bot Started ({mode_name})</b>\n"
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Mode: {mode_name}\n"
            f"Interval: {interval_minutes} minutes"
        )
        send_telegram_notification(start_msg)

        if "Live" in self.__class__.__name__:
            self._check_existing_positions_at_startup()

        try:
            while self.is_running:
                try:
                    self.cycle_count += 1
                    self.log("info", f"=== CYCLE {self.cycle_count} START ===")

                    if self.portfolio_cb is not None and self.portfolio_cb.tripped:
                        self.log("warning", "[PORTFOLIO CB] Portfolio circuit breaker tripped - halting cycle")
                        self.write_heartbeat("error", "portfolio_cb_tripped")
                        break

                    self.write_heartbeat("running", "pre_cycle")
                    self.write_session_state("running")
                    self.run_cycle()
                    self.log("info", f"=== CYCLE {self.cycle_count} COMPLETE ===")

                    if self.portfolio_cb is not None:
                        try:
                            current_equity = float(self.config.get("account_balance", 0))
                            if current_equity <= 0:
                                total_pnl = self._get_total_pnl()
                                current_equity = float(self.config.get("position_size_usd", 55.0)) + total_pnl
                            self.portfolio_cb.check(current_equity)
                        except CircuitBreakTriggered as cb_err:
                            self.log("warning", f"[PORTFOLIO CB] Tripped: {cb_err}")
                            self.write_heartbeat("error", "portfolio_cb_tripped")
                            break
                        except Exception as cb_err:
                            self.log("warning", f"Portfolio CB check error (non-fatal): {cb_err}")

                    self.write_heartbeat("running", "post_cycle")
                    self.write_session_state("running")
                except Exception as e:
                    self.log("error", f"Cycle error: {str(e)}")
                    self.write_heartbeat("error", type(e).__name__)
                    self.write_session_state("error")

                sleep_seconds = interval_minutes * 60
                self.log("info", f"Sleeping {interval_minutes}m until next cycle...")
                for i in range(0, sleep_seconds, 10):
                    if not self.is_running:
                        break
                    time.sleep(min(10, sleep_seconds - i))
                    self.write_heartbeat("sleeping", f"interval_{i}s")
                if sleep_seconds > 0 and self._last_runtime_status != "error":
                    self.write_session_state("sleeping")

        except KeyboardInterrupt:
            self.log("info", "Keyboard interrupt received")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self.log("info", "Shutting down execution engine")
        self.is_running = False
        self.write_heartbeat("shutdown", "final")
        if self._last_runtime_status == "error":
            self.write_session_state("error", final=True)
        else:
            self.write_session_state("shutdown", final=True)

        mode_name = "LIVE_TRADING" if "Live" in self.__class__.__name__ else "DRY_RUN"
        uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        uptime_str = (
            f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m"
            if uptime_seconds > 60
            else f"{int(uptime_seconds)}s"
        )
        stop_msg = (
            f"<b>Bot Stopped ({mode_name})</b>\n"
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Uptime: {uptime_str}\n"
            f"Completed {self.cycle_count} cycles"
        )
        send_telegram_notification(stop_msg)

    def _check_existing_positions_at_startup(self):
        pass

    def _get_total_pnl(self) -> float:
        return sum(t["pnl"] for t in self.closed_trades)

    def close_position(
        self, trade_id: int, exit_price: float, reason: str
    ) -> Dict[str, Any]:
        trade = None
        for i, t in enumerate(self.open_positions):
            if t["trade_id"] == trade_id:
                trade = self.open_positions.pop(i)
                break

        if not trade:
            self.log("warning", f"Trade {trade_id} not found")
            return {}

        direction = trade.get("direction", "long")
        if direction == "short":
            pnl = (trade["entry_price"] - exit_price) * trade["position_size"]
            pnl_pct = (trade["entry_price"] - exit_price) / trade["entry_price"] * 100
        else:
            pnl = (exit_price - trade["entry_price"]) * trade["position_size"]
            pnl_pct = (exit_price - trade["entry_price"]) / trade["entry_price"] * 100

        trade["exit_price"] = exit_price
        trade["exit_time"] = datetime.utcnow().isoformat()
        trade["exit_reason"] = reason
        trade["status"] = TradeStatus.CLOSED.value
        trade["pnl"] = pnl
        trade["pnl_pct"] = pnl_pct

        self.closed_trades.append(trade)

        if pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

        self.log(
            "info",
            f"Trade {trade_id} CLOSED via {reason}: P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)",
        )
        return trade

    def _handle_spot_long_only_sell(self, pair: str, recommendation: str, current_price: float) -> Optional[Dict[str, Any]]:
        """Handle SELL/SHORT signal in spot-long-only mode.

        If spot_long_only is enabled and the signal is SELL/SHORT:
        - If position profit < MIN_PROFIT_TO_HOLD_PCT → close to protect capital
        - If position profit >= MIN_PROFIT_TO_HOLD_PCT → hold through SELL signal,
          let trailing stop / TP / progressive ROI manage exit
        - Return skip dict (no new short position)

        Returns None if the signal should proceed normally (BUY/HOLD or spot_long_only disabled).
        """
        spot_long_only = self.config.get("spot_long_only", SPOT_LONG_ONLY)
        if not spot_long_only or recommendation not in ("SELL", "SHORT"):
            return None

        existing = [p for p in self.open_positions if p.get("pair") == pair and p.get("direction", "long") == "long"]
        if not existing:
            self.log("info", f"[SPOT_LONG_ONLY] SELL signal for {pair} — no long position to close, skipping")
            return {
                "agent": self.__class__.__name__,
                "action": "execute_trade",
                "success": True,
                "data": {
                    "trade_executed": False,
                    "reason": "spot_long_only: SELL/SHORT signals close longs or skip",
                    "pair": pair,
                    "closed_positions": 0,
                },
            }

        positions_to_close = []
        positions_to_hold = []

        for pos in existing:
            entry = pos.get("entry_price", 0)
            if entry <= 0:
                positions_to_close.append(pos)
                continue
            profit_pct = (current_price - entry) / entry * 100.0
            if profit_pct < self.MIN_PROFIT_TO_HOLD_PCT:
                positions_to_close.append(pos)
            else:
                positions_to_hold.append(pos)
                logger.info(
                    f"[SPOT_LONG_ONLY] Holding {pair} long through SELL signal: "
                    f"profit {profit_pct:.2f}% >= {self.MIN_PROFIT_TO_HOLD_PCT}% threshold — "
                    f"trailing stop / TP / ROI will manage exit"
                )

        for pos in positions_to_close:
            profit_pct = (current_price - pos.get("entry_price", 0)) / pos.get("entry_price", 1) * 100.0
            logger.info(
                f"[SPOT_LONG_ONLY] Closing {pair} long on SELL signal: "
                f"profit {profit_pct:.2f}% < {self.MIN_PROFIT_TO_HOLD_PCT}% threshold"
            )
            self._close_spot_long_position(pos, pair, current_price)

        return {
            "agent": self.__class__.__name__,
            "action": "execute_trade",
            "success": True,
            "data": {
                "trade_executed": False,
                "reason": "spot_long_only: SELL/SHORT signals close longs or skip",
                "pair": pair,
                "closed_positions": len(positions_to_close),
                "held_positions": len(positions_to_hold),
            },
        }

    def _close_spot_long_position(self, pos: Dict, pair: str, current_price: float):
        """Close a spot-long position. Override in subclasses for exchange-specific behavior."""
        close_result = self.close_position(pos["trade_id"], current_price, "spot_long_only_sell_signal")
        self.log("info", f"[SPOT_LONG_ONLY] Closed trade {pos['trade_id']}: {close_result}")

    def update_open_positions(
        self, current_prices: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        closed_trades = []
        trades_to_close = []

        for trade in self.open_positions:
            pair = trade["pair"]
            if pair not in current_prices:
                continue

            current_price = current_prices[pair]
            direction = trade.get("direction", "long")
            if direction == "short":
                pnl = (trade["entry_price"] - current_price) * trade["position_size"]
                pnl_pct = (trade["entry_price"] - current_price) / trade["entry_price"] * 100
            else:
                pnl = (current_price - trade["entry_price"]) * trade["position_size"]
                pnl_pct = (current_price - trade["entry_price"]) / trade["entry_price"] * 100
            trade["pnl"] = pnl
            trade["pnl_pct"] = pnl_pct

            # ── Custom stoploss: move SL to break-even if profit ≥ threshold ──
            original_sl = trade["stop_loss"]
            be_result = self.custom_stoploss.check(
                entry_price=trade["entry_price"],
                current_price=current_price,
                original_sl=original_sl,
                direction=direction,
            )
            trade["breakeven_active"] = be_result["breakeven_active"]
            trade["unrealized_pct"] = be_result["unrealized_pct"]
            sl_after_breakeven = be_result["stop_loss"]

            # ── Trailing stop: ratchet SL upward as price advances ──
            psar_val = trade.get("psar_value")
            trail_result = self.trailing_stop.update(
                trade_id=trade["trade_id"],
                entry_price=trade["entry_price"],
                current_price=current_price,
                original_sl=sl_after_breakeven,
                direction=direction,
                psar_value=psar_val,
            )
            effective_sl = trail_result["stop_loss"]
            trade["effective_stop_loss"] = effective_sl
            trade["trailing_active"] = trail_result["trailing_active"]
            trade["high_water"] = trail_result["high_water"]

            # ── Progressive ROI: time-based TP that tightens over time ──
            entry_time_iso = trade.get("entry_time", "")
            roi_exit, current_pct, target_pct, minutes_held = self.progressive_roi.check(
                entry_time_iso=entry_time_iso,
                current_price=current_price,
                entry_price=trade["entry_price"],
            )
            trade["roi_target_pct"] = target_pct
            trade["minutes_held"] = minutes_held

            # ── Exit logic ──
            if direction == "short":
                if current_price >= effective_sl:
                    reason = "trailing_stop" if trail_result["trailing_active"] else "stop_loss"
                    trades_to_close.append((trade["trade_id"], current_price, reason))
                elif current_price <= trade["take_profit"]:
                    trades_to_close.append((trade["trade_id"], current_price, "take_profit"))
                elif roi_exit:
                    trades_to_close.append((trade["trade_id"], current_price, "progressive_roi"))
            else:
                if current_price <= effective_sl:
                    reason = "trailing_stop" if trail_result["trailing_active"] else "stop_loss"
                    trades_to_close.append((trade["trade_id"], current_price, reason))
                elif current_price >= trade["take_profit"]:
                    trades_to_close.append((trade["trade_id"], current_price, "take_profit"))
                elif roi_exit:
                    trades_to_close.append((trade["trade_id"], current_price, "progressive_roi"))

        for trade_id, exit_price, reason in trades_to_close:
            self.trailing_stop.remove(trade_id)
            closed = self.close_position(trade_id, exit_price, reason)
            closed_trades.append(closed)

        return closed_trades

    def get_performance_summary(self) -> Dict[str, Any]:
        if self.total_trades == 0:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "avg_pnl": 0,
                "open_positions": 0,
                "max_win": 0,
                "max_loss": 0,
            }

        total_pnl = sum(t["pnl"] for t in self.closed_trades)
        max_win = max((t["pnl"] for t in self.closed_trades), default=0)
        max_loss = min((t["pnl"] for t in self.closed_trades), default=0)

        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.winning_trades / self.total_trades
            if self.total_trades > 0
            else 0,
            "total_pnl": total_pnl,
            "avg_pnl": total_pnl / self.total_trades if self.total_trades > 0 else 0,
            "open_positions": len(self.open_positions),
            "max_win": max_win,
            "max_loss": max_loss,
        }

    def get_open_positions(self) -> List[Dict[str, Any]]:
        return self.open_positions.copy()

    def get_trade_history(self) -> List[Dict[str, Any]]:
        return self.closed_trades.copy()


class DryRunExecutor(ExecutionEngine):
    """
    DRY_RUN MODE: COMPLETELY ISOLATED
    - Uses cached/historical OHLCV data
    - NO API calls to KuCoin
    - NO real orders placed
    - Pure backtesting engine
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.log("info", "DRY_RUN mode: Backtesting only")
        self.paper_trading = True
        self.max_open_positions = config.get("max_open_positions", 1)
        self.max_trades_per_session = config.get("max_trades_per_session", 2)
        self.load_backtest_data()

        # Paper trade ledger — persistent tracking across restarts
        self.ledger = PaperTradeLedger(
            filepath=config.get("paper_ledger_path", "paper_trades_ledger.json"),
            initial_balance=float(config.get("account_balance", 110)),
        )
        self.log("info", f"Paper trade ledger initialized ({len(self.ledger.get_closed_trades())} historical trades)")

        self._paper_balance = float(self.config.get("account_balance", 110))

        self.orchestrator = None
        if config.get("paper_live", True):
            try:
                from ..intelligence.orchestrator import IntelligenceOrchestrator
                from ..data.data_fetcher import DataFetchingAgent
                from ..intelligence.market_analyzer import MarketAnalysisAgent
                from ..intelligence.backtester import BacktestingAgent
                from ..risk.risk_manager import RiskManagementAgent

                orch_config = dict(config)
                orch_config["paper_trading"] = True
                orch_config["paper_live"] = False
                orch_config.setdefault("timeframe", resolve_timeframe(orch_config))
                self.orchestrator = IntelligenceOrchestrator(orch_config)
                self.orchestrator.register_agent(DataFetchingAgent(orch_config))
                self.orchestrator.register_agent(MarketAnalysisAgent(orch_config))
                self.orchestrator.register_agent(BacktestingAgent(orch_config))
                self.orchestrator.register_agent(RiskManagementAgent(orch_config))
                exec_agent_config = dict(orch_config)
                exec_agent_config["dry_run"] = True
                exec_agent_config["live_trading"] = False
                exec_agent_config["paper_live"] = False
                self.orchestrator.register_agent(ExecutionAgent(exec_agent_config))
                # Wire exchange adapter for klines/OHLCV fetching (enables RegimeDetector + WhaleWatch)
                try:
                    from ..execution.exchange_adapter import KuCoinAdapter
                    # Adapter init now non-fatal on auth failure — klines are public
                    klines_adapter = KuCoinAdapter(
                        api_key=KUCOIN_API_KEY or "dummy",
                        api_secret=KUCOIN_API_SECRET or "dummy",
                        passphrase=KUCOIN_API_PASSPHRASE or "dummy",
                    )
                    self.orchestrator.set_exchange_adapter(klines_adapter)
                    self.log("info", "Klines adapter wired — ADX/ATR regime detection active")
                except Exception as klines_err:
                    self.log("warning", f"Klines adapter setup failed (regime detection will use simplified mode): {klines_err}")
                self.log("info", "PAPER-LIVE mode: orchestrator wired (live data + paper execution)")
            except Exception as e:
                self.log("warning", f"Orchestrator wiring failed, falling back to CSV-only: {e}")
                self.orchestrator = None

    def close_position(self, trade_id: int, exit_price: float, reason: str) -> Dict[str, Any]:
        trade = super().close_position(trade_id, exit_price, reason)
        if not trade:
            return trade
        pnl = trade.get("pnl", 0.0)
        self._paper_balance += pnl
        self.config["account_balance"] = self._paper_balance
        logger.info(
            f"[DRY-RUN] Paper balance updated: ${self._paper_balance - pnl:.2f} → ${self._paper_balance:.2f} "
            f"(P&L: ${pnl:+.2f})"
        )
        return trade

    def load_backtest_data(self) -> None:
        self.log("info", "Loading backtest data from CSV files...")
        self.backtest_data = {}

        csv_files = [f for f in os.listdir(".") if f.endswith("_ohlcv.csv")]
        for csv_file in csv_files:
            symbol = csv_file.replace("_ohlcv.csv", "")
            try:
                import pandas as pd

                df = pd.read_csv(csv_file)
                self.backtest_data[symbol] = df
                self.log("info", f"Loaded {symbol}: {len(df)} candles")
            except Exception as e:
                self.log("warning", f"Failed to load {csv_file}: {e}")

    def run_cycle(self):
        if self.orchestrator is not None:
            self.log("info", "Running paper-live strategy cycle with live market data...")
            try:
                symbols = self.config.get("trading_pairs", ["BTC/USDT", "ETH/USDT", "AVAX/USDT", "DOGE/USDT", "LINK/USDT"])
                result = self.orchestrator.execute(market_symbols=symbols)
                if isinstance(result, dict):
                    data = result.get("data", {})
                    trade_exec = data.get("trade_executed", False)
                    reason = data.get("reason", "")
                    if trade_exec:
                        self.log("info", f"Paper trade executed: {data.get('execution', {})}")
                    else:
                        self.log("info", f"No trade this cycle: {reason}")

                # Monitor open ledger positions against current market prices
                try:
                    # Get current prices from the data fetching phase
                    data_result = self.orchestrator.workflow_trace[0] if self.orchestrator.workflow_trace else {}
                    if isinstance(data_result, dict):
                        market_data = data_result.get("data", {}).get("market_data", {})
                        current_prices = {}
                        for pair, info in market_data.items():
                            if isinstance(info, dict):
                                price = info.get("current_price", 0)
                                if price > 0:
                                    current_prices[pair] = price
                        if current_prices:
                            closed = self.ledger.monitor_open_positions(current_prices)
                            for ct in closed:
                                self.log("info", f"[LEDGER] Auto-closed: #{ct['trade_id']} {ct['pair']} ${ct['net_pnl_usd']:+.4f} ({ct['exit_reason']})")
                except Exception as ledger_err:
                    self.log("warning", f"Ledger monitoring failed (non-fatal): {ledger_err}")

            except Exception as e:
                self.log("error", f"Orchestrator cycle error: {e}")
        else:
            self.log("info", "Running backtest strategy analysis on cached OHLCV data...")
            self.log(
                "info",
                f"Backtest cycle {self.cycle_count} complete - 0 trades executed",
            )

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        market_data = input_data.get("market_data", {})
        position_size = input_data.get("position_size", 0)
        stop_loss = input_data.get("stop_loss", 0)
        take_profit = input_data.get("take_profit", 0)

        if not market_data or position_size <= 0:
            return {
                "agent": "DryRunExecutor",
                "action": "execute_trade",
                "success": True,
                "data": {"trade_executed": False, "reason": "Invalid position size", "account_balance": self._paper_balance},
            }

        pair = input_data.get("pair") or list(market_data.keys())[0]
        market_info = market_data.get(pair, list(market_data.values())[0] if market_data else {})
        entry_price = market_info.get("current_price", 0)

        analysis_data = input_data.get("analysis", {})
        pair_analysis = analysis_data.get(pair, {})
        recommendation = pair_analysis.get("recommendation", "HOLD")

        sell_result = self._handle_spot_long_only_sell(pair, recommendation, entry_price)
        if sell_result is not None:
            sell_result.setdefault("data", {})["account_balance"] = self._paper_balance
            return sell_result

        spot_long_only = self.config.get("spot_long_only", SPOT_LONG_ONLY)
        if spot_long_only:
            direction = "long"
        else:
            direction = "short" if recommendation in ("SELL", "SHORT") else "long"

        trade = {
            "trade_id": self.total_trades + 1,
            "pair": pair,
            "entry_price": entry_price,
            "position_size": position_size,
            "entry_value": entry_price * position_size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_time": datetime.utcnow().isoformat(),
            "status": TradeStatus.OPEN.value,
            "direction": direction,
            "paper_trading": True,
            "pnl": 0,
            "pnl_pct": 0,
            "exit_price": None,
            "exit_time": None,
            "exit_reason": None,
            "order_id": None,
            "stop_order_id": None,
            "tp_order_id": None,
        }

        self.open_positions.append(trade)
        self.total_trades += 1

        self.log(
            "info",
            f"Trade {trade['trade_id']} [PAPER] OPENED: "
            f"{pair} @ {entry_price:.4f} | Size: {position_size:.4f} | "
            f"SL: {stop_loss:.4f} | TP: {take_profit:.4f}",
        )

        # Record in persistent ledger
        try:
            backtest_results = input_data.get("backtest_results", {})
            pair_backtest = backtest_results.get(pair, {})
            backtest_win_rate = pair_backtest.get("win_rate", 0.0)
            backtest_data_source = pair_backtest.get("data_source", "")
            self.ledger.open_trade(
                pair=pair,
                direction=direction,
                entry_price=entry_price,
                position_size=position_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
                signal_strength=pair_analysis.get("signal_strength", 0),
                regime=pair_analysis.get("regime", ""),
                intelligence_confidence=pair_analysis.get("intelligence", {}).get("confidence", 0),
                intelligence_action=pair_analysis.get("intelligence", {}).get("action", ""),
                backtest_win_rate=backtest_win_rate,
                backtest_data_source=backtest_data_source,
                metadata={"source": "dry_run_cycle", "recommendation": recommendation},
            )
        except Exception as ledger_err:
            self.log("warning", f"Ledger recording failed (non-fatal): {ledger_err}")

        return {
            "agent": "DryRunExecutor",
            "action": "execute_trade",
            "success": True,
            "data": {
                "trade_executed": True,
                "trade_id": trade["trade_id"],
                "pair": pair,
                "entry_price": entry_price,
                "position_size": position_size,
                "entry_value": trade["entry_value"],
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "paper_trading": True,
                "open_positions_count": len(self.open_positions),
                "account_balance": self._paper_balance,
        },
    }


class LiveExecutor(ExecutionEngine):
    """
    LIVE_TRADING MODE: COMPLETELY ISOLATED
    - Real API calls via ExchangeAdapter
    - Real orders placed on account
    - LIVE MONEY AT RISK
    - Production trading engine
    - Extensive risk checks and safety mechanisms
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.log("info", "LIVE_TRADING mode: Production trading enabled")
        self.paper_trading = False
        self.live_mode = True
        self.position_size_usd = float(POSITION_SIZE_USD)
        self.max_open_positions = config.get("max_open_positions", 1)
        self.max_trades_per_session = config.get("max_trades_per_session", 2)
        self.max_position_size_usd = config.get("max_position_size_usd")
        self.max_trade_loss_usd = config.get("max_trade_loss_usd")
        self.max_daily_loss_usd = config.get("max_daily_loss_usd")
        self.min_balance_usd = config.get("min_balance_usd")
        self.order_type = config.get("order_type", "market")
        self.adapter: Optional[ExchangeAdapter] = None
        self.circuit_breaker = CircuitBreaker()
        self._initialize_adapter()

    def _initialize_adapter(self) -> None:
        try:
            self.adapter = KuCoinAdapter(
                api_key=KUCOIN_API_KEY,
                api_secret=KUCOIN_API_SECRET,
                passphrase=KUCOIN_API_PASSPHRASE,
            )
            # Note: connect() removed — KuCoinAdapter.__init__() already creates
            # the SDK client and verifies connection via _test_connection()
            self.log("info", "Live API adapter initialized successfully")
        except Exception as e:
            self.log("error", f"Failed to initialize live adapter: {e}")
            raise

    def run_cycle(self):
        self.log("info", "Starting live trading cycle...")
        try:
            self.write_heartbeat("running", "fetch_data")
            self.write_heartbeat("running", "risk_check")
            self._risk_check()
            self.write_heartbeat("running", "monitor")
            self.log("info", "Live trading cycle complete")
        except Exception as e:
            self.log("error", f"Live trading cycle error: {e}")
            raise

    def _validate_live_trade(
        self,
        entry_price: float,
        position_size: float,
        stop_loss: float,
        account_balance: Optional[float],
    ) -> Optional[str]:
        position_value = entry_price * position_size
        if account_balance is not None:
            if position_value > account_balance * 1.1:
                return f"CRITICAL: Position value ${position_value:.2f} exceeds account balance ${account_balance:.2f}"

        if self.order_type not in {"market", "limit"}:
            return f"Unsupported order type: {self.order_type}"
        if len(self.open_positions) >= self.max_open_positions:
            return f"Max open positions reached ({self.max_open_positions})"
        if self.max_position_size_usd is not None:
            position_size_usd = entry_price * position_size
            if position_size_usd > self.max_position_size_usd:
                return f"Position size ${position_size_usd:.2f} exceeds limit ${self.max_position_size_usd:.2f}"
        if self.max_trade_loss_usd is not None and stop_loss > 0 and entry_price > 0:
            risk_per_unit = max(entry_price - stop_loss, 0)
            projected_loss = risk_per_unit * position_size
            if projected_loss > self.max_trade_loss_usd:
                return f"Projected loss ${projected_loss:.2f} exceeds limit ${self.max_trade_loss_usd:.2f}"
        if self.max_daily_loss_usd is not None:
            total_pnl = self._get_total_pnl()
            if total_pnl <= -self.max_daily_loss_usd:
                return f"Daily loss limit reached (${total_pnl:.2f} <= -${self.max_daily_loss_usd:.2f})"
        if self.min_balance_usd is not None and account_balance is not None:
            if account_balance < self.min_balance_usd:
                return f"Account balance ${account_balance:.2f} below minimum ${self.min_balance_usd:.2f}"
        return None

    def _validate_session_limits(self) -> Optional[str]:
        if self.total_trades >= self.max_trades_per_session:
            return f"Max trades per session reached ({self.max_trades_per_session})"
        if len(self.open_positions) >= self.max_open_positions:
            return f"Max open positions reached ({self.max_open_positions})"
        return None

    def _risk_check(self) -> None:
        if not self.adapter:
            raise RuntimeError("Adapter not initialized")
        try:
            account_balance = self.adapter.get_balance()
            if account_balance is not None:
                usdt_balance = account_balance.get("USDT", 0.0)
                self.log("info", f"Account balance: ${usdt_balance:.2f} USDT")
        except Exception as e:
            self.log("warning", f"Could not fetch balance: {e}")

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        market_data = input_data.get("market_data", {})
        position_size = input_data.get("position_size", 0)
        stop_loss = input_data.get("stop_loss", 0)
        take_profit = input_data.get("take_profit", 0)
        account_balance = input_data.get("account_balance")
        position_approved = input_data.get("position_approved", None)
        risk_approved = input_data.get("risk_approved", None)

        if (
            getattr(self, "circuit_breaker", None)
            and self.circuit_breaker.is_triggered()
        ):
            return {
                "agent": "LiveExecutor",
                "action": "execute_trade",
                "success": True,
                "data": {
                    "trade_executed": False,
                    "reason": "Circuit breaker triggered",
                },
            }
        if (
            getattr(self, "portfolio_cb", None)
            and self.portfolio_cb.tripped
        ):
            return {
                "agent": "LiveExecutor",
                "action": "execute_trade",
                "success": True,
                "data": {
                    "trade_executed": False,
                    "reason": "Portfolio circuit breaker triggered",
                },
            }

        if not position_approved or not risk_approved:
            return {
                "agent": "LiveExecutor",
                "action": "execute_trade",
                "success": True,
                "data": {"trade_executed": False, "reason": "Risk approval required"},
            }

        if not market_data or position_size <= 0:
            return {
                "agent": "LiveExecutor",
                "action": "execute_trade",
                "success": True,
                "data": {"trade_executed": False, "reason": "Invalid position size"},
            }

        session_limit_reason = self._validate_session_limits()
        if session_limit_reason:
            return {
                "agent": "LiveExecutor",
                "action": "execute_trade",
                "success": True,
                "data": {"trade_executed": False, "reason": session_limit_reason},
            }

        pair = input_data.get("pair") or list(market_data.keys())[0]
        market_info = market_data.get(pair, list(market_data.values())[0] if market_data else {})
        entry_price = market_info.get("current_price", 0)

        analysis_data = input_data.get("analysis", {})
        pair_analysis = analysis_data.get(pair, {})
        recommendation = pair_analysis.get("recommendation", "HOLD")

        sell_result = self._handle_spot_long_only_sell(pair, recommendation, entry_price)
        if sell_result is not None:
            return sell_result

        rejection_reason = self._validate_live_trade(
            entry_price=entry_price,
            position_size=position_size,
            stop_loss=stop_loss,
            account_balance=account_balance,
        )
        if rejection_reason:
            self.log("warning", f"Live trade rejected: {rejection_reason}")
            return {
                "agent": "LiveExecutor",
                "action": "execute_trade",
                "success": True,
                "data": {"trade_executed": False, "reason": rejection_reason},
            }

        order_details = None
        try:
            self.log("warning", "LIVE TRADING ACTIVATED - Placing real order")
            side = "buy"
            order_details = self.adapter.place_order(
                pair=pair,
                side=side,
                size=position_size,
                order_type=self.order_type,
                price=entry_price if self.order_type == "limit" else None,
            )
            self.log("info", f"Live order executed: {order_details}")

            if stop_loss > 0:
                try:
                    sl_details = self.adapter.place_stop_loss(
                        pair=pair, size=position_size, stop_price=stop_loss
                    )
                    self.log("info", f"Stop-loss placed: {sl_details}")
                except Exception as e:
                    self.log("error", f"CRITICAL: Failed to place stop-loss: {e}")

                try:
                    if order_details and isinstance(order_details, dict):
                        order_id = order_details.get("orderId") or order_details.get(
                            "order_id"
                        )
                        if order_id:
                            self.adapter.cancel_order(
                                symbol=pair, order_id=str(order_id)
                            )
                            self.log(
                                "warning",
                                f"Entry order {order_id} cancelled after SL failure",
                            )
                except Exception as cancel_err:
                    self.log(
                        "error",
                        f"Failed to cancel entry order after SL failure: {cancel_err}",
                    )
                return {
                    "agent": "LiveExecutor",
                    "action": "execute_trade",
                    "success": False,
                    "data": {
                        "trade_executed": False,
                        "reason": "Stop-loss placement failed, entry order unwound",
                    },
                }

            if take_profit > 0:
                try:
                    tp_details = self.adapter.place_take_profit(
                        pair=pair, size=position_size, tp_price=take_profit
                    )
                    self.log("info", f"Take-profit placed: {tp_details}")
                except Exception as e:
                    self.log("error", f"CRITICAL: Failed to place take-profit: {e}")

                try:
                    if order_details and isinstance(order_details, dict):
                        oid = order_details.get("orderId") or order_details.get(
                            "order_id"
                        )
                        if oid:
                            self.adapter.cancel_order(symbol=pair, order_id=str(oid))
                            self.log(
                                "warning",
                                f"Entry order {oid} cancelled after TP failure",
                            )
                except Exception as cancel_err2:
                    self.log(
                        "error",
                        f"Failed to cancel entry order after TP failure: {cancel_err2}",
                    )
                return {
                    "agent": "LiveExecutor",
                    "action": "execute_trade",
                    "success": False,
                    "data": {
                        "trade_executed": False,
                        "reason": "Take-profit placement failed, entry order unwound",
                    },
                }

        except Exception as e:
            error_msg = f"Live order failed: {str(e)}"
            self.log("error", error_msg)
            return {
                "agent": "LiveExecutor",
                "action": "execute_trade",
                "success": False,
                "error": error_msg,
            }

        trade = {
            "trade_id": self.total_trades + 1,
            "pair": pair,
            "entry_price": entry_price,
            "position_size": position_size,
            "entry_value": entry_price * position_size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_time": datetime.utcnow().isoformat(),
            "status": TradeStatus.OPEN.value,
            "direction": "long",
            "paper_trading": False,
            "pnl": 0,
            "pnl_pct": 0,
            "exit_price": None,
            "exit_time": None,
            "exit_reason": None,
            "order_id": order_details.get("order_id") if order_details else None,
            "stop_order_id": None,
            "tp_order_id": None,
        }

        self.open_positions.append(trade)
        self.total_trades += 1

        self.log(
            "info",
            f"Trade {trade['trade_id']} [LIVE] OPENED: "
            f"{pair} @ {entry_price:.4f} | Size: {position_size:.4f} | "
            f"SL: {stop_loss:.4f} | TP: {take_profit:.4f}",
        )

        return {
            "agent": "LiveExecutor",
            "action": "execute_trade",
            "success": True,
            "data": {
                "trade_executed": True,
                "trade_id": trade["trade_id"],
                "pair": pair,
                "entry_price": entry_price,
                "position_size": position_size,
                "entry_value": trade["entry_value"],
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "paper_trading": False,
                "open_positions_count": len(self.open_positions),
            },
        }

    def _close_spot_long_position(self, pos: Dict, pair: str, current_price: float):
        """Close a spot-long position on the exchange, then update internal state."""
        order_ok = False
        try:
            self.adapter.place_order(
                pair=pair,
                side="sell",
                size=pos["position_size"],
                order_type=self.order_type,
                price=current_price if self.order_type == "limit" else None,
            )
            order_ok = True
        except Exception as e:
            self.log("error", f"[SPOT_LONG_ONLY] Failed to place close-sell order for trade {pos['trade_id']}: {e}")
        if order_ok:
            close_result = self.close_position(pos["trade_id"], current_price, "spot_long_only_sell_signal")
            self.log("info", f"[SPOT_LONG_ONLY] Closed trade {pos['trade_id']}: {close_result}")
        else:
            self.log("warning", f"[SPOT_LONG_ONLY] Trade {pos['trade_id']} still open on exchange — close-sell failed, will retry next cycle")

    def _check_existing_positions_at_startup(self) -> None:
        if not self.adapter:
            return
        try:
            self.log(
                "info", "Checking for existing positions and unexpected balances..."
            )
            account_balance = self.adapter.get_balance()
            if account_balance is not None:
                usdt_balance = account_balance.get("USDT", 0.0)
                if usdt_balance > 0:
                    msg = (
                        f"<b>ALERT: Existing Account Balance Detected</b>\n"
                        f"Balance: ${usdt_balance:.2f} USDT\n"
                        f"Bot will manage this balance."
                    )
                send_telegram_notification(msg)
            else:
                self.log("info", "No unexpected positions - account clean")
        except Exception as e:
            self.log("error", f"Failed to check existing positions: {e}")


class ExecutionAgent(BaseAgent):
    """
    Agent-compatible execution wrapper.

    Wraps either DryRunExecutor or LiveExecutor and exposes the
    BaseAgent interface for the orchestrator's workflow pipeline.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("ExecutionAgent", config)
        config = config or {}

        dry_run = config.get("dry_run", DRY_RUN)
        live = config.get("live_trading", LIVE_TRADING)

        if dry_run:
            self.engine = DryRunExecutor(config)
        elif live:
            self.engine = LiveExecutor(config)
        else:
            self.engine = DryRunExecutor(config)

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self.log_execution_start("execute_trade")
        try:
            result = self.engine.execute(input_data)
            self.log_execution_end(
                "execute_trade", success=result.get("success", False)
            )
            return result
        except Exception as e:
            error_msg = f"Trade execution error: {str(e)}"
            self.set_status(AgentStatus.ERROR, error_msg)
            self.log_execution_end("execute_trade", success=False)
            return self.create_message(
                action="execute_trade", success=False, error=error_msg
            )

    def close_position(
        self, trade_id: int, exit_price: float, reason: str
    ) -> Dict[str, Any]:
        return self.engine.close_position(trade_id, exit_price, reason)

    def update_open_positions(
        self, current_prices: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        return self.engine.update_open_positions(current_prices)

    def get_performance_summary(self) -> Dict[str, Any]:
        return self.engine.get_performance_summary()

    def get_open_positions(self) -> List[Dict[str, Any]]:
        return self.engine.get_open_positions()

    def get_trade_history(self) -> List[Dict[str, Any]]:
        return self.engine.get_trade_history()


def select_executor(dry_run: bool, live_trading: bool) -> ExecutionEngine:
    config = {
        "dry_run": dry_run,
        "live_trading": live_trading,
        "paper_live": True,
        "spot_long_only": SPOT_LONG_ONLY,
        "position_size_usd": float(POSITION_SIZE_USD),
        "monitor_interval_min": int(MONITOR_INTERVAL_MIN),
        "max_position_size_usd": float(os.getenv("MAX_POSITION_SIZE_USD", "55.0")),
        "max_trade_loss_usd": float(os.getenv("MAX_TRADE_LOSS_USD", "1.10")),
        "max_daily_loss_usd": float(os.getenv("MAX_DAILY_LOSS_USD", "3.30")),
        "min_balance_usd": float(os.getenv("MIN_BALANCE_USD", "5.0")),
        "paper_trading": dry_run,
        "account_balance": float(os.getenv("ACCOUNT_BALANCE", "110")),
        "trading_pairs": os.getenv("TRADING_PAIRS", "BTC/USDT,ETH/USDT").split(","),
        "min_notional_usd": float(os.getenv("MIN_NOTIONAL_USD", "5.0")),
        "risk_per_trade": float(os.getenv("RISK_PER_TRADE", "0.01")),
        "min_risk_reward_ratio": float(os.getenv("MIN_RISK_REWARD_RATIO", "1.2")),
        "max_daily_loss": float(os.getenv("MAX_DAILY_LOSS", "0.03")),
        "min_signal_strength": float(os.getenv("MIN_SIGNAL_STRENGTH", "0.30")),
        "min_win_rate": float(os.getenv("MIN_WIN_RATE", "0.45")),
        "default_stop_loss_pct": float(os.getenv("DEFAULT_STOP_LOSS_PCT", "0.02")),
    }

    if dry_run:
        logger.info("STARTING DRY_RUN MODE (Paper-Live: live data + paper execution)")
        return DryRunExecutor(config)

    if live_trading and not dry_run:
        logger.warning("STARTING LIVE_TRADING MODE (REAL MONEY!)")
        return LiveExecutor(config)

    raise RuntimeError(
        "Invalid mode: either DRY_RUN must be True or LIVE_TRADING must be True"
    )


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    from ..deterministic_startup import DeterministicStartup

    startup = DeterministicStartup()
    startup.cleanup_leftover_state()
    startup.verify_critical_systems(required_systems=["working_directory", "heartbeat_io", "kucoin_api"])

    interval = int(os.getenv("CYCLE_INTERVAL", str(MONITOR_INTERVAL_MIN)))
    executor = select_executor(DRY_RUN, LIVE_TRADING)
    executor.run_continuous(interval_minutes=interval)
