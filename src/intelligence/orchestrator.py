"""
Intelligence Orchestrator - The Brain + Workflow Conductor
==========================================================
Coordinates all intelligence modules AND manages the full agent workflow.

Merged from:
- kucoin-margin-bot IntelligenceOrchestrator: regime/lead-lag/whale intelligence,
  regime guard variations (v0-v4), position multiplier decisions
- Deliberate-AI-Ensemble OrchestratorAgent: WorkflowStage state machine,
  SNOEPILE FREEZE/THAW protocol, agent registry, circuit breaker integration,
  notional rejection handler, daily risk reset, post-cycle safety audit

Decision Matrix:
1. If Lead-Lag says DANGER -> Exit everything immediately
2. If Regime says TRENDING_DOWN -> No longs (variation-dependent)
3. If Regime says RANGING + Whale says ABSORPTION -> Strong buy
4. If Regime says RANGING + No whale activity -> Normal RSI strategy
5. Workflow: FETCH -> ANALYZE (intelligence) -> BACKTEST -> RISK -> EXECUTE -> MONITOR -> AUDIT
"""

import os
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from enum import Enum
from typing import Any, Dict, List, Optional

import pandas as pd

from ..base_agent import BaseAgent, AgentStatus
from ..config import REGIME_GUARD_MODE
from ..risk.circuit_breaker import CircuitBreaker
from ..risk.portfolio_circuit_breaker import (
    PortfolioCircuitBreaker,
    CircuitBreakTriggered,
)
from .regime_detector import RegimeDetector
from .lead_lag import LeadLagMonitor
from .whale_watch import WhaleWatch
from ..data.kucoin_klines_fetcher import KuCoinKlinesFetcher

logger = logging.getLogger(__name__)

DEFAULT_ACCOUNT_BALANCE = 10000.0
DEFAULT_NOTIONAL_REJECTION_THRESHOLD = 10
DEFAULT_NOTIONAL_PAUSE_DURATION_HOURS = 1.0
COOLDOWN_HOURS = 4
COOLDOWN_SECONDS = COOLDOWN_HOURS * 3600
V4_ADX_THRESHOLD = 50
V2_CONSECUTIVE_DOWNTREND_LIMIT = 2
MIN_ACCOUNT_BALANCE_RECOMMENDATION = 500
LEAD_LAG_DANGER_CONFIDENCE = 1.0
LEAD_LAG_DANGER_MULTIPLIER = 0.0
TRENDING_DOWN_CONFIDENCE = 0.9
TRENDING_DOWN_MULTIPLIER = 0.0
WHALE_BULLISH_CONFIDENCE_THRESHOLD = 0.6
WHALE_BULLISH_SIGNAL_CONFIDENCE = 0.95
WHALE_BULLISH_SIGNAL_MULTIPLIER = 1.0
WHALE_BEARISH_CONFIDENCE = 0.8
WHALE_BEARISH_MULTIPLIER = 0.0
REDUCE_SIZE_CONFIDENCE = 0.5
REDUCE_SIZE_MULTIPLIER = 0.5
RSI_APPROVED_CONFIDENCE = 0.7
RSI_APPROVED_MULTIPLIER = 1.0
NO_SIGNAL_CONFIDENCE = 0.3
NO_SIGNAL_MULTIPLIER = 0.8
V1_SOFT_HALT_CONFIDENCE = 0.7
V1_SOFT_HALT_MULTIPLIER = 0.25
V2_PROBE_CONFIDENCE = 0.6
V2_PROBE_MULTIPLIER = 0.5
V3_PROBE_CONFIDENCE = 0.6
V3_PROBE_MULTIPLIER = 0.5
V3_HALT_CONFIDENCE = 0.9
V3_HALT_MULTIPLIER = 0.0
V4_HALT_CONFIDENCE = 0.9
V4_HALT_MULTIPLIER = 0.0
V4_PROBE_CONFIDENCE = 0.6
V4_PROBE_MULTIPLIER = 0.5


class WorkflowStage(Enum):
    IDLE = "idle"
    WAITING_FOR_NEXT_CYCLE = "waiting_for_next_cycle"
    FETCHING_DATA = "fetching_data"
    ANALYZING_MARKET = "analyzing_market"
    BACKTESTING = "backtesting"
    RISK_ASSESSMENT = "risk_assessment"
    EXECUTING = "executing"
    MONITORING = "monitoring"
    ERROR = "error"
    PAUSED = "paused"


class IntelligenceOrchestrator(BaseAgent):
    """
    The Master Intelligence Coordinator + Workflow Conductor.

    Aggregates signals from all intelligence modules, outputs actionable
    decisions, AND manages the full agent workflow pipeline.

    REGIME GUARD VARIATIONS (controlled via REGIME_GUARD_MODE env var):
    - "v0_baseline": Full halt on TRENDING_DOWN (position_multiplier = 0.0)
    - "v1_soft_halt": Reduced position size during downtrends (0.25x)
    - "v2_two_candle": Require 2 consecutive TRENDING_DOWN signals before halting
    - "v3_cooldown": Allow probe trades after 4h without new lows
    - "v4_threshold": Adjust ADX/ATR sensitivity (ADX > 50 instead of 40)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("IntelligenceOrchestrator", config)
        config = config or {}

        enable_regime = config.get("enable_regime", True)
        enable_lead_lag = config.get("enable_lead_lag", True)
        enable_whale = config.get("enable_whale", True)

        self.regime_detector = RegimeDetector() if enable_regime else None
        self.lead_lag = LeadLagMonitor() if enable_lead_lag else None
        self.whale_watch = WhaleWatch() if enable_whale else None

        self.enabled_modules = {
            "regime": enable_regime,
            "lead_lag": enable_lead_lag,
            "whale": enable_whale,
        }

        self.regime_guard_mode = os.getenv("REGIME_GUARD_MODE", REGIME_GUARD_MODE)

        self.consecutive_downtrend_count: Dict[str, int] = {}
        self.cooldown_override_active: Dict[str, float] = {}

        self.current_stage = WorkflowStage.IDLE
        self.workflow_history: List[Dict[str, Any]] = []
        self.workflow_trace: List[Dict[str, Any]] = []
        self.trading_paused = False
        self.pause_reason: Optional[str] = None
        self.pause_timestamp: Optional[datetime] = None
        self.resume_warning_given = False
        self._cb_state_path = os.getenv("CB_STATE_PATH", "cb_state.json")
        self.circuit_breaker_active = False
        self._load_cb_state()
        self.agent_registry: Dict[str, BaseAgent] = {}
        self.is_paper_trading = config.get("paper_trading", True)
        self._last_daily_reset: Optional[str] = None
        self._cycle_count = 0
        self._account_balance = config.get("account_balance", DEFAULT_ACCOUNT_BALANCE)
        self._start_time = time.time()
        self.portfolio_cb = PortfolioCircuitBreaker(
            starting_equity=self._account_balance,
            state_path=os.getenv("PORTFOLIO_CB_STATE_PATH", "portfolio_cb_state.json"),
        )

        try:
            cb_config = config.get("circuit_breaker", {})
            self.circuit_breaker = CircuitBreaker(
                loss_threshold_pct=cb_config.get("loss_threshold_pct", 8.0),
                time_window_minutes=cb_config.get("time_window_minutes", 60),
                check_interval_seconds=cb_config.get("check_interval_seconds", 300),
                name="OrchestratorCB",
            )
        except Exception as e:
            self.logger.warning(f"CircuitBreaker init failed, using no-op fallback: {e}")
            self.circuit_breaker = None

        # Klines/OHLCV fetcher for RegimeDetector + WhaleWatch
        self._klines_fetcher: Optional[KuCoinKlinesFetcher] = None
        self._exchange_adapter = None  # set via set_exchange_adapter()

        self.consecutive_notional_rejections = 0
        self.notional_rejection_threshold = config.get(
            "notional_rejection_threshold", DEFAULT_NOTIONAL_REJECTION_THRESHOLD
        )
        self.notional_pause_duration_hours = config.get(
            "notional_pause_duration_hours", DEFAULT_NOTIONAL_PAUSE_DURATION_HOURS
        )

        self.logger.setLevel(logging.DEBUG)
        self.logger.info(
            f"IntelligenceOrchestrator initialized: {self.enabled_modules}"
        )
        self.logger.info(f"Regime Guard Mode: {self.regime_guard_mode}")

    def register_agent(self, agent: BaseAgent) -> None:
        self.agent_registry[agent.agent_name] = agent
        self.logger.info(f"Registered agent: {agent.agent_name}")

    def set_exchange_adapter(self, adapter) -> None:
        """Set the exchange adapter for kline data fetching.

        The adapter must implement get_klines(symbol, interval, start, end).
        This enables RegimeDetector and WhaleWatch to receive live OHLCV data.
        """
        self._exchange_adapter = adapter
        self._klines_fetcher = KuCoinKlinesFetcher(
            default_interval="5min",
            default_candle_count=100,
            cache_enabled=True,
        )
        self.logger.info("Exchange adapter set — klines/OHLCV fetching enabled")

        # Also wire to BacktestingAgent if registered
        backtest_agent = self.agent_registry.get("BacktestingAgent")
        if backtest_agent and hasattr(backtest_agent, "set_klines_infrastructure"):
            backtest_agent.set_klines_infrastructure(self._klines_fetcher, adapter)

    def pause_trading(self, reason: str) -> None:
        self.trading_paused = True
        self.pause_reason = reason
        self.pause_timestamp = datetime.now()
        self.resume_warning_given = False
        self.set_status(AgentStatus.PAUSED, f"Trading paused: {reason}")
        self.logger.warning(
            f"[WARN] SNOEPILE FREEZE: Trading paused at "
            f"{self.pause_timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {reason}"
        )

    def resume_trading(self, reason: str = "Manual resume") -> None:
        pause_duration = None
        if self.pause_timestamp:
            pause_duration = (
                datetime.now() - self.pause_timestamp
            ).total_seconds() / 3600

        self.trading_paused = False
        old_reason = self.pause_reason
        self.pause_reason = None
        self.pause_timestamp = None
        self.resume_warning_given = False
        self.set_status(AgentStatus.IDLE)

        duration_str = (
            f" (paused for {pause_duration:.1f} hours)" if pause_duration else ""
        )
        self.logger.info(
            f"[INFO] SNOEPILE THAW: Trading resumed{duration_str} - "
            f"Reason: {reason} | Previous pause: {old_reason}"
        )

    def activate_circuit_breaker(self, reason: str) -> None:
        self.circuit_breaker_active = True
        self.trading_paused = True
        self.pause_reason = f"Circuit breaker: {reason}"
        self.set_status(AgentStatus.ERROR, f"Circuit breaker activated: {reason}")
        self._persist_cb_state(reason)
        self.logger.critical(f"[CRITICAL] CIRCUIT BREAKER ACTIVATED: {reason}")

    def _load_cb_state(self) -> None:
        try:
            if os.path.exists(self._cb_state_path):
                with open(self._cb_state_path, "r") as f:
                    state = json.load(f)
                if state.get("active"):
                    self.circuit_breaker_active = True
                    self.trading_paused = True
                    self.pause_reason = (
                        f"Circuit breaker (persisted): {state.get('reason', 'unknown')}"
                    )
                    self.logger.warning(
                        f"[WARN] Restored circuit breaker state from {self._cb_state_path}: {state.get('reason')}"
                    )
        except Exception:
            pass

    def _persist_cb_state(self, reason: str = "") -> None:
        state = {
            "active": self.circuit_breaker_active,
            "reason": reason,
            "timestamp": time.time(),
        }
        try:
            with open(self._cb_state_path, "w") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def reset_circuit_breaker(self, reason: str = "Manual reset") -> None:
        self.circuit_breaker_active = False
        self.trading_paused = False
        self.pause_reason = None
        self._persist_cb_state("")
        self.set_status(AgentStatus.IDLE)
        self.logger.info(f"[INFO] Circuit breaker reset: {reason}")

    def is_trading_allowed(self) -> tuple[bool, Optional[str]]:
        if self.circuit_breaker_active:
            return False, "Circuit breaker is active"
        if self.trading_paused:
            return False, self.pause_reason
        return True, None

    def _handle_notional_rejection(
        self, rejection_reason: str, risk_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        self.consecutive_notional_rejections += 1

        assessments = risk_data.get("assessments", {})
        first_pair = list(assessments.keys())[0] if assessments else "Unknown"
        pair = (
            assessments.get(first_pair, {}).get("pair", first_pair)
            if assessments
            else "Unknown"
        )
        account_balance = risk_data.get("account_balance", 0)

        self.logger.info(
            f"[INTELLIGENCE] Trade signal valid but position size rejected due to minimum notional constraints. "
            f"This is expected behavior with current account balance ${account_balance:.2f}. "
            f"Continuing to monitor. (Consecutive: {self.consecutive_notional_rejections})"
        )

        if self.consecutive_notional_rejections >= self.notional_rejection_threshold:
            pause_message = (
                f"Detected {self.consecutive_notional_rejections} consecutive minimum notional rejections. "
                f"Account balance (${account_balance:.2f}) is below effective trading threshold for {pair}. "
                f"RECOMMENDATION: Increase account balance to ${MIN_ACCOUNT_BALANCE_RECOMMENDATION}+ or adjust risk parameters. "
                f"Pausing trading for {self.notional_pause_duration_hours} hour(s) to avoid unnecessary cycles."
            )
            self.logger.warning(f"[ADAPTIVE INTELLIGENCE] {pause_message}")
            self.pause_trading(
                f"Account too small for minimum notional (${account_balance:.2f})"
            )
            self.consecutive_notional_rejections = 0
            return self.create_message(
                action="orchestrate_workflow",
                success=True,
                data={
                    "trade_executed": False,
                    "reason": "notional_rejection_pause",
                    "intelligence": pause_message,
                    "recommendation": f"Increase account balance to ${MIN_ACCOUNT_BALANCE_RECOMMENDATION}+ or adjust risk parameters",
                    "pause_duration_hours": self.notional_pause_duration_hours,
                },
            )

        return self.create_message(
            action="orchestrate_workflow",
            success=True,
            data={
                "trade_executed": False,
                "reason": "notional_rejection",
                "consecutive_count": self.consecutive_notional_rejections,
                "threshold": self.notional_rejection_threshold,
            },
        )

    def transition_stage(
        self, new_stage: WorkflowStage, metadata: Optional[Dict] = None
    ) -> None:
        old_stage = self.current_stage
        self.current_stage = new_stage
        self.workflow_history.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "from_stage": old_stage.value,
                "to_stage": new_stage.value,
                "metadata": metadata or {},
            }
        )
        self.logger.info(f"Workflow: {old_stage.value} -> {new_stage.value}")

    def _reset_daily_risk_if_needed(self) -> None:
        today = datetime.utcnow().date().isoformat()
        if self._last_daily_reset == today:
            return
        risk_agent = self.agent_registry.get("RiskManagementAgent")
        if risk_agent and hasattr(risk_agent, "reset_daily_risk"):
            risk_agent.reset_daily_risk()
            self.logger.info("Daily risk reset executed")
        self._last_daily_reset = today

    def _update_account_balance_if_provided(self, exec_result: Dict[str, Any]) -> None:
        exec_data = exec_result.get("data", {}) if isinstance(exec_result, dict) else {}
        new_balance = exec_data.get("account_balance") or exec_data.get("balance")
        if new_balance is None:
            return
        self._account_balance = float(new_balance)
        risk_agent = self.agent_registry.get("RiskManagementAgent")
        if risk_agent and hasattr(risk_agent, "update_account_balance"):
            risk_agent.update_account_balance(self._account_balance)
            self.logger.info(f"Account balance updated from execution: {new_balance}")

    def _validate_agent_output(
        self,
        result: Dict[str, Any],
        agent_name: str,
        required_data_keys: Optional[List[str]] = None,
    ) -> bool:
        if not isinstance(result, dict):
            self.activate_circuit_breaker(f"{agent_name} returned non-dict response")
            return False
        if result.get("success") is False:
            return True
        data = result.get("data")
        if not isinstance(data, dict):
            self.activate_circuit_breaker(
                f"{agent_name} returned malformed data payload"
            )
            return False
        if required_data_keys:
            missing = [k for k in required_data_keys if k not in data]
            if missing:
                self.activate_circuit_breaker(
                    f"{agent_name} missing required fields: {', '.join(missing)}"
                )
                return False
        return True

    def _validate_market_data(self, market_data: Dict[str, Any]) -> bool:
        if not isinstance(market_data, dict) or not market_data:
            return False
        for pair, data in market_data.items():
            if not isinstance(data, dict):
                return False
            price = data.get("current_price")
            if not isinstance(price, (int, float)) or price <= 0:
                self.logger.error("Unexpected market data for %s: %s", pair, data)
                return False
        return True

    def _execute_agent_phase(
        self, agent_name: str, action: str, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        if agent_name not in self.agent_registry:
            error_msg = f"Agent {agent_name} not registered"
            self.logger.error(error_msg)
            return self.create_message(
                action=action,
                success=False,
                error=error_msg,
                data={"agent": agent_name},
            )
        try:
            agent = self.agent_registry[agent_name]
            self.logger.debug(f"Executing {agent_name}.{action}")
            result = agent.execute(input_data)
            self.workflow_trace.append(result)
            return result
        except Exception as e:
            error_msg = f"{agent_name} execution failed: {str(e)}"
            self.logger.error(error_msg)
            return self.create_message(
                action=action,
                success=False,
                error=error_msg,
                data={"agent": agent_name},
            )

    def analyze_market(
        self,
        df: pd.DataFrame,
        order_book: Optional[Dict] = None,
        symbol: str = None,
    ) -> Dict:
        """
        Run full intelligence analysis.

        Returns:
        {
            "action": "BUY" | "SELL" | "HOLD" | "EXIT_ALL",
            "confidence": 0.0-1.0,
            "position_multiplier": 0.0-1.0,
            "reasoning": str,
            "regime": {...},
            "lead_lag": {...},
            "whale": {...}
        }
        """
        results: Dict[str, Any] = {
            "regime": None,
            "lead_lag": None,
            "whale": None,
        }

        if self.regime_detector:
            results["regime"] = self.regime_detector.analyze(df)

        if self.lead_lag:
            results["lead_lag"] = self.lead_lag.get_status()

        if self.whale_watch:
            results["whale"] = self.whale_watch.analyze_order_flow(df, order_book)

        action, confidence, multiplier, reasoning = self._make_decision(results, symbol)

        return {
            "action": action,
            "confidence": confidence,
            "position_multiplier": multiplier,
            "reasoning": reasoning,
            **results,
        }

    def _make_decision(
        self, results: Dict, symbol: str = None
    ) -> tuple[str, float, float, str]:
        if results["lead_lag"] and results["lead_lag"]["signal"] == "DANGER":
            return (
                "EXIT_ALL",
                LEAD_LAG_DANGER_CONFIDENCE,
                LEAD_LAG_DANGER_MULTIPLIER,
                "LEAD-LAG DANGER: Binance cascade detected, exiting all positions",
            )

        if results["regime"]:
            regime = results["regime"]

            if regime["recommendation"] == "HALT_TRADING":
                if self.regime_guard_mode == "v1_soft_halt":
                    return self._handle_v1_soft_halt(regime)
                elif self.regime_guard_mode == "v2_two_candle":
                    return self._handle_v2_two_candle(regime, symbol)
                elif self.regime_guard_mode == "v3_cooldown":
                    return self._handle_v3_cooldown(regime, symbol)
                elif self.regime_guard_mode == "v4_threshold":
                    return self._handle_v4_threshold(regime, symbol)
                else:
                    return (
                        "HOLD",
                        TRENDING_DOWN_CONFIDENCE,
                        TRENDING_DOWN_MULTIPLIER,
                        f"TRENDING_DOWN detected (ADX: {regime['adx']:.1f}), no longs",
                    )

            if results["whale"] and regime["recommendation"] == "USE_RSI":
                whale = results["whale"]

                if (
                    whale["signal"] == "BULLISH_ABSORPTION"
                    and whale["confidence"] > WHALE_BULLISH_CONFIDENCE_THRESHOLD
                ):
                    return (
                        "BUY",
                        WHALE_BULLISH_SIGNAL_CONFIDENCE,
                        WHALE_BULLISH_SIGNAL_MULTIPLIER,
                        f"STRONG SIGNAL: Ranging market + Whale absorption "
                        f"(CVD: {whale['cvd_ratio']:.1%})",
                    )

                elif whale["signal"] == "BEARISH_DISTRIBUTION":
                    return ("SELL", WHALE_BEARISH_CONFIDENCE, WHALE_BEARISH_MULTIPLIER, "Whales distributing, exit positions")

            if regime["recommendation"] == "REDUCE_SIZE":
                return (
                    "HOLD",
                    REDUCE_SIZE_CONFIDENCE,
                    REDUCE_SIZE_MULTIPLIER,
                    f"High volatility regime (ATR: {regime['atr_pct']:.2f}%), "
                    f"reduced position sizing",
                )

            elif regime["recommendation"] == "USE_RSI":
                return (
                    "HOLD",
                    RSI_APPROVED_CONFIDENCE,
                    RSI_APPROVED_MULTIPLIER,
                    f"Ranging market (ADX: {regime['adx']:.1f}), RSI strategy approved",
                )

        return (
            "HOLD",
            NO_SIGNAL_CONFIDENCE,
            NO_SIGNAL_MULTIPLIER,
            "No strong intelligence signal, proceeding with caution",
        )

    def _handle_v1_soft_halt(self, regime: Dict) -> tuple:
        return (
            "HOLD",
            V1_SOFT_HALT_CONFIDENCE,
            V1_SOFT_HALT_MULTIPLIER,
            f"V1_SOFT_HALT: Downtrend detected (ADX: {regime['adx']:.1f}), "
            f"reduced to 25% position size for probe trades",
        )

    def _handle_v2_two_candle(self, regime: Dict, symbol: str) -> tuple:
        if symbol is None:
            symbol = "UNKNOWN"

        self.consecutive_downtrend_count[symbol] = (
            self.consecutive_downtrend_count.get(symbol, 0) + 1
        )

        if self.consecutive_downtrend_count[symbol] >= V2_CONSECUTIVE_DOWNTREND_LIMIT:
            return (
                "HOLD",
                TRENDING_DOWN_CONFIDENCE,
                TRENDING_DOWN_MULTIPLIER,
                f"V2_TWO_CANDLE: {self.consecutive_downtrend_count[symbol]} consecutive "
                f"TRENDING_DOWN signals (ADX: {regime['adx']:.1f}), halting",
            )
        else:
            return (
                "HOLD",
                V2_PROBE_CONFIDENCE,
                V2_PROBE_MULTIPLIER,
                f"V2_TWO_CANDLE: 1st downtrend signal ({self.consecutive_downtrend_count[symbol]}/2), "
                f"probing with 50% position size",
            )

    def _handle_v3_cooldown(self, regime: Dict, symbol: str) -> tuple:
        if symbol is None:
            symbol = "UNKNOWN"

        current_time = time.time()
        last_low_time = self.cooldown_override_active.get(symbol, current_time)

        if current_time - last_low_time > COOLDOWN_SECONDS:
            return (
                "HOLD",
                V3_PROBE_CONFIDENCE,
                V3_PROBE_MULTIPLIER,
                f"V3_COOLDOWN: {COOLDOWN_HOURS}h since last low, probing with 50% position size "
                f"(ADX: {regime['adx']:.1f})",
            )
        else:
            hours_left = (COOLDOWN_SECONDS - (current_time - last_low_time)) / 3600
            return (
                "HOLD",
                V3_HALT_CONFIDENCE,
                V3_HALT_MULTIPLIER,
                f"V3_COOLDOWN: Cooldown active ({hours_left:.1f}h remaining), "
                f"no trades until recovery confirmed (ADX: {regime['adx']:.1f})",
            )

    def _handle_v4_threshold(self, regime: Dict, symbol: str) -> tuple:
        adx = regime.get("adx", 0)

        if adx > V4_ADX_THRESHOLD:
            return (
                "HOLD",
                V4_HALT_CONFIDENCE,
                V4_HALT_MULTIPLIER,
                f"V4_THRESHOLD: Strong downtrend (ADX: {adx:.1f} > {V4_ADX_THRESHOLD}), halting",
            )
        else:
            return (
                "HOLD",
                V4_PROBE_CONFIDENCE,
                V4_PROBE_MULTIPLIER,
                f"V4_THRESHOLD: Mild downtrend (ADX: {adx:.1f} < {V4_ADX_THRESHOLD}), "
                f"probing with 50% position size",
            )

    def should_allow_rsi_buy(self, analysis: Dict) -> bool:
        return (
            analysis["action"] in ["BUY", "HOLD"]
            and analysis["position_multiplier"] > 0
        )

    def should_emergency_exit(self, analysis: Dict) -> bool:
        return analysis["action"] == "EXIT_ALL"

    def get_position_size_adjustment(self, analysis: Dict) -> float:
        return analysis["position_multiplier"]

    def execute(self, market_symbols: List[str], *args, **kwargs) -> Dict[str, Any]:
        """
        Execute the main orchestration workflow.

        Steps:
        1. Daily risk reset
        2. Check trading allowed
        3. Fetch data
        4. Intelligence analysis (regime + whale + lead-lag)
        5. SNOEPILE auto-resume check
        6. Backtest
        7. Risk assessment
        8. Execute trade
        9. Monitor (unconditional)
        10. Audit (unconditional)
        """
        self.log_execution_start("orchestrate_trading_workflow")
        cycle_start = time.time()

        cycle_results: Dict[str, Any] = {
            "data_result": None,
            "analysis_result": None,
            "intelligence_result": None,
            "backtest_result": None,
            "risk_result": None,
            "exec_result": None,
            "final_result": None,
        }

        try:
            self._reset_daily_risk_if_needed()

            allowed, reason = self.is_trading_allowed()
            if not allowed:
                cycle_results["final_result"] = self.create_message(
                    action="orchestrate_workflow",
                    success=False,
                    error=f"Trading not allowed: {reason}",
                    data={"trading_allowed": False, "reason": reason},
                )
                return cycle_results["final_result"]

            self.logger.info(f"Starting workflow for symbols: {market_symbols}")

            self.transition_stage(WorkflowStage.FETCHING_DATA)
            data_result = self._execute_agent_phase(
                "DataFetchingAgent", "fetch_data", {"symbols": market_symbols}
            )
            cycle_results["data_result"] = data_result

            if not data_result["success"]:
                self.activate_circuit_breaker("Data fetching failed")
                cycle_results["final_result"] = data_result
                return data_result

            if not self._validate_agent_output(
                data_result, "DataFetchingAgent", ["market_data"]
            ):
                cycle_results["final_result"] = self.create_message(
                    action="orchestrate_workflow",
                    success=False,
                    error="Unexpected DataFetchingAgent response",
                )
                return cycle_results["final_result"]

            market_data = data_result.get("data", {}).get("market_data", {})
            if not self._validate_market_data(market_data):
                self.logger.error("No market data returned from DataFetchingAgent")
                self.activate_circuit_breaker(
                    "Data fetching returned empty market data"
                )
                cycle_results["final_result"] = self.create_message(
                    action="orchestrate_workflow",
                    success=False,
                    error="Empty market data from DataFetchingAgent",
                )
                return cycle_results["final_result"]

            self.transition_stage(WorkflowStage.ANALYZING_MARKET)
            analysis_result = self._execute_agent_phase(
                "MarketAnalysisAgent",
                "analyze_market",
                {"market_data": market_data},
            )
            cycle_results["analysis_result"] = analysis_result

            if not analysis_result["success"]:
                self.logger.error("Market analysis failed - BLOCKING TRADES")
                cycle_results["final_result"] = analysis_result
                return analysis_result
            if not self._validate_agent_output(
                analysis_result, "MarketAnalysisAgent", ["analysis", "regime"]
            ):
                cycle_results["final_result"] = self.create_message(
                    action="orchestrate_workflow",
                    success=False,
                    error="Unexpected MarketAnalysisAgent response",
                )
                return cycle_results["final_result"]
            analysis_data = analysis_result.get("data", {})
            market_regime = analysis_data.get("regime", "unknown")

            # ── Klines/OHLCV Intelligence: RegimeDetector + WhaleWatch ──
            if self._klines_fetcher and self._exchange_adapter:
                try:
                    for pair in market_symbols:
                        df = self._klines_fetcher.fetch_klines(
                            self._exchange_adapter, pair
                        )
                        if df is not None and not df.empty and len(df) >= 15:
                            # Run ADX/ATR-based regime detection
                            regime_result = self.regime_detector.analyze(df) if self.regime_detector else None
                            # Run whale order flow analysis
                            whale_result = self.whale_watch.analyze_order_flow(df) if self.whale_watch else None

                        # Run full intelligence analysis (combines regime + whale + lead-lag)
                        intel_analysis = self.analyze_market(df, symbol=pair)
                        pair_analysis_from_market = analysis_data.get("analysis", {}).get(pair, {})
                        if isinstance(pair_analysis_from_market, dict):
                            intel_confidence = intel_analysis.get("confidence", 0.0)
                            intel_multiplier = intel_analysis.get("position_multiplier", 1.0)
                            intel_action = intel_analysis.get("action", "HOLD")
                            base_strength = pair_analysis_from_market.get("signal_strength", 0.0)
                            if intel_action in ("BUY",) and intel_confidence > 0.6:
                                boost = intel_confidence * intel_multiplier
                                boosted_strength = min(1.0, base_strength + boost * 0.15)
                                pair_analysis_from_market["signal_strength"] = boosted_strength
                                pair_analysis_from_market["intelligence_boost"] = {
                                    "base_strength": base_strength,
                                    "boost": boost * 0.15,
                                    "intel_action": intel_action,
                                    "intel_confidence": intel_confidence,
                                    "intel_multiplier": intel_multiplier,
                                }
                                self.logger.info(
                                    f"[INTELLIGENCE] {pair} signal_strength boosted: "
                                    f"{base_strength:.3f} → {boosted_strength:.3f} "
                                    f"(action={intel_action}, confidence={intel_confidence:.2f}, "
                                    f"multiplier={intel_multiplier:.2f})"
                                )
                            elif intel_action == "EXIT_ALL":
                                pair_analysis_from_market["signal_strength"] = 0.0
                                pair_analysis_from_market["intelligence_boost"] = {
                                    "base_strength": base_strength,
                                    "boost": -base_strength,
                                    "intel_action": intel_action,
                                    "intel_confidence": intel_confidence,
                                    "intel_multiplier": 0.0,
                                }
                                self.logger.warning(
                                    f"[INTELLIGENCE] {pair} signal_strength killed: "
                                    f"EXIT_ALL from intelligence"
                                )
                            pair_analysis_from_market["intelligence"] = {
                                "action": intel_action,
                                "confidence": intel_confidence,
                                "position_multiplier": intel_multiplier,
                                "reasoning": intel_analysis.get("reasoning", ""),
                            }

                        intel = {
                            "pair": pair,
                            "regime": regime_result,
                            "whale": whale_result,
                        }
                        cycle_results["intelligence_result"] = intel

                        # ADX-based regime can override the simplistic MarketAnalysisAgent regime
                        if regime_result and regime_result.get("regime") != "UNKNOWN":
                            adx_regime = regime_result["regime"]
                            adx_rec = regime_result.get("recommendation", "")
                            self.logger.info(
                                f"[INTELLIGENCE] ADX regime for {pair}: {adx_regime} "
                                f"(ADX: {regime_result.get('adx', 0):.1f}, "
                                f"ATR: {regime_result.get('atr_pct', 0):.2f}%, "
                                f"rec: {adx_rec})"
                            )
                            # ADX regime can override MarketAnalysisAgent's simplistic regime
                            # ADX is more nuanced — trust it over the simple price-based check
                            if adx_rec == "HALT_TRADING":
                                market_regime = "bearish"
                            elif adx_regime == "RANGING_HIGH_VOL":
                                # High vol ranging — downgrade from bullish to neutral
                                if market_regime == "bullish":
                                    market_regime = "neutral"
                                # Upgrade from bearish to neutral — ADX says ranging, not trending down
                                elif market_regime == "bearish":
                                    market_regime = "neutral"
                                    self.logger.info(
                                        f"[INTELLIGENCE] ADX override: {pair} bearish→neutral "
                                        f"(ADX says RANGING_HIGH_VOL, not trending down)"
                                    )
                            elif adx_regime in ("RANGING_LOW_VOL", "UNKNOWN") and market_regime == "bearish":
                                # Low-vol ranging or unknown ADX — also upgrade bearish to neutral
                                market_regime = "neutral"
                                self.logger.info(
                                    f"[INTELLIGENCE] ADX override: {pair} bearish→neutral "
                                    f"(ADX says {adx_regime}, not confirming downtrend)"
                                )

                        if whale_result:
                            self.logger.info(
                                f"[INTELLIGENCE] Whale signal for {pair}: "
                                f"{whale_result.get('signal', 'NEUTRAL')} "
                                f"(CVD: {whale_result.get('cvd_ratio', 0.5):.1%})"
                            )
                    else:
                        self.logger.debug(
                            f"[INTELLIGENCE] No OHLCV data for {pair}, "
                            f"using MarketAnalysisAgent regime only"
                        )
                except Exception as e:
                    self.logger.warning(f"[INTELLIGENCE] Klines analysis failed (non-fatal): {e}")


            if self.trading_paused and not self.circuit_breaker_active:
                if market_regime in ["neutral", "bullish"]:
                    if not self.resume_warning_given:
                        self.resume_warning_given = True
                        self.logger.info(
                            f"[INFO] SNOEPILE WARMING: Market regime is {market_regime}. "
                            f"Will auto-resume next cycle if conditions hold."
                        )
                        cycle_results["final_result"] = self.create_message(
                            action="orchestrate_workflow",
                            success=True,
                            data={
                                "trading_paused": True,
                                "resume_warning": True,
                                "regime": market_regime,
                            },
                        )
                        return cycle_results["final_result"]
                    else:
                        self.resume_trading(
                            f"Auto-resume: Market regime improved to {market_regime}"
                        )
                        self.logger.info(
                            f"[INFO] Auto-resumed trading - market regime: {market_regime}"
                        )
                else:
                    self.resume_warning_given = False

            skip_execution = False
            if market_regime == "bearish" and not self.trading_paused:
                self.pause_trading(
                    "Bearish market regime detected - downtrend protection active"
                )
                self.logger.warning(
                    "[BEARISH] Bearish regime detected — will run backtest+risk for visibility, skip execution"
                )
                skip_execution = True

            if self.trading_paused and not skip_execution:
                # Trading paused for non-bearish reasons (circuit breaker, manual pause) — skip pipeline
                cycle_results["final_result"] = self.create_message(
                    action="orchestrate_workflow",
                    success=True,
                    data={"trading_paused": True, "reason": self.pause_reason},
                )
                return cycle_results["final_result"]

            self.transition_stage(WorkflowStage.BACKTESTING)
            backtest_result = self._execute_agent_phase(
                "BacktestingAgent",
                "backtest_signals",
                {
                    "market_data": market_data,
                    "analysis": analysis_data.get("analysis", {}),
                },
            )
            cycle_results["backtest_result"] = backtest_result

            if not backtest_result["success"]:
                self.logger.error("Backtesting failed - BLOCKING TRADES")
                cycle_results["final_result"] = backtest_result
                return backtest_result
            if not self._validate_agent_output(
                backtest_result, "BacktestingAgent", ["backtest_results"]
            ):
                cycle_results["final_result"] = self.create_message(
                    action="orchestrate_workflow",
                    success=False,
                    error="Unexpected BacktestingAgent response",
                )
                return cycle_results["final_result"]

            backtest_data = backtest_result.get("data", {})

            self.transition_stage(WorkflowStage.RISK_ASSESSMENT)
            risk_result = self._execute_agent_phase(
                "RiskManagementAgent",
                "assess_and_size_position",
                {
                    "market_data": market_data,
                    "analysis": analysis_data.get("analysis", {}),
                    "backtest_results": backtest_data.get("backtest_results", {}),
                },
            )
            cycle_results["risk_result"] = risk_result

            if not risk_result["success"]:
                self.logger.error("Risk assessment failed - BLOCKING TRADES")
                cycle_results["final_result"] = risk_result
                return risk_result
            if not self._validate_agent_output(
                risk_result, "RiskManagementAgent", ["position_approved"]
            ):
                cycle_results["final_result"] = self.create_message(
                    action="orchestrate_workflow",
                    success=False,
                    error="Unexpected RiskManagementAgent response",
                )
                return cycle_results["final_result"]

            risk_data = risk_result["data"]

            if not risk_data.get("position_approved", False):
                rejection_reason = risk_data.get("rejection_reason")
                self.logger.warning(
                    f"Position rejected by risk manager: {rejection_reason}"
                )
                reason_lower = (rejection_reason or "").lower()

                if "daily loss limit" in reason_lower or "risk limit" in reason_lower:
                    self.activate_circuit_breaker("Risk limit hit - trading halted")
                    cycle_results["final_result"] = self.create_message(
                        action="orchestrate_workflow",
                        success=False,
                        error="Risk limit hit - trading halted",
                    )
                    return cycle_results["final_result"]

                if "notional" in reason_lower and "below minimum" in reason_lower:
                    cycle_results["final_result"] = self._handle_notional_rejection(
                        rejection_reason, risk_data
                    )
                    return cycle_results["final_result"]

                self.consecutive_notional_rejections = 0
                cycle_results["final_result"] = self.create_message(
                    action="orchestrate_workflow",
                    success=True,
                    data={"trade_executed": False, "reason": "risk_rejection"},
                )
                return cycle_results["final_result"]

            self.consecutive_notional_rejections = 0

            if self.circuit_breaker is not None and self.circuit_breaker.is_triggered():
                self.logger.warning("[CIRCUIT BREAKER] Orchestrator circuit breaker is tripped - skipping trade")
                cycle_results["final_result"] = self.create_message(
                    action="orchestrate_workflow",
                    success=True,
                    data={
                        "trade_executed": False,
                        "reason": "Orchestrator circuit breaker tripped",
                    },
                )
                return cycle_results["final_result"]

            if skip_execution:
                self.logger.info("[BEARISH] Skipping execution — bearish regime active, backtest+risk completed for visibility")
                exec_result = self.create_message(
                    action="execute_trade",
                    success=True,
                    data={"trade_executed": False, "reason": "bearish_regime_skip"},
                )
            else:
                self.transition_stage(WorkflowStage.EXECUTING)
            exec_result = self._execute_agent_phase(
                "ExecutionAgent",
                "execute_trade",
                {
                    "market_data": market_data,
                    "position_size": risk_data.get("position_size"),
                    "stop_loss": risk_data.get("stop_loss"),
                    "take_profit": risk_data.get("take_profit"),
                    "paper_trading": self.is_paper_trading,
                    "account_balance": risk_data.get("account_balance"),
                    "position_approved": risk_data.get("position_approved", False),
                    "risk_approved": risk_data.get("position_approved", False),
                    "analysis": analysis_data.get("analysis", {}),
                    "backtest_results": backtest_data.get("backtest_results", {}),
                },
            )
            cycle_results["exec_result"] = exec_result

            if not self._validate_agent_output(
                exec_result, "ExecutionAgent", ["trade_executed"]
            ):
                cycle_results["final_result"] = self.create_message(
                    action="orchestrate_workflow",
                    success=False,
                    error="Unexpected ExecutionAgent response",
                )
                return cycle_results["final_result"]

            self._update_account_balance_if_provided(exec_result)

            if self.circuit_breaker is not None:
                try:
                    trade_pnl = 0.0
                    exec_data = exec_result.get("data", {}) if isinstance(exec_result, dict) else {}
                    if isinstance(exec_data, dict):
                        trade_pnl = float(exec_data.get("pnl", 0.0))
                    ok, reason = self.circuit_breaker.check_circuit(trade_pnl)
                    if not ok:
                        self.logger.warning(f"[CIRCUIT BREAKER] Check failed after trade: {reason}")
                except Exception as e:
                    self.logger.warning(f"CircuitBreaker check_circuit error (non-fatal): {e}")

            cycle_results["final_result"] = self.create_message(
                action="orchestrate_workflow",
                success=True,
                data={
                    "trade_executed": exec_result.get("success", False),
                    "analysis": analysis_data,
                    "risk_assessment": risk_data,
                    "execution": exec_result.get("data", {}),
                    "workflow_history_length": len(self.workflow_history),
                },
            )

            self.transition_stage(WorkflowStage.WAITING_FOR_NEXT_CYCLE)
            self.log_execution_end("orchestrate_trading_workflow", success=True)
            return cycle_results["final_result"]

        except Exception as e:
            error_msg = f"Orchestration error: {str(e)}"
            self.activate_circuit_breaker(error_msg)
            self.log_execution_end("orchestrate_trading_workflow", success=False)
            cycle_results["final_result"] = self.create_message(
                action="orchestrate_workflow", success=False, error=error_msg
            )
            return cycle_results["final_result"]

        finally:
            self.transition_stage(WorkflowStage.MONITORING)
            if "MonitoringAgent" in self.agent_registry:
                self._execute_agent_phase(
                    "MonitoringAgent",
                    "log_and_monitor",
                    {
                        "workflow_stage": WorkflowStage.MONITORING.value,
                        "workflow_trace": self.workflow_trace,
                        "data_result": cycle_results.get("data_result"),
                        "analysis_result": cycle_results.get("analysis_result"),
                        "backtest_result": cycle_results.get("backtest_result"),
                        "risk_result": cycle_results.get("risk_result"),
                        "exec_result": cycle_results.get("exec_result"),
                        "final_result": cycle_results.get("final_result"),
                    },
                )

            audit_data: Dict[str, Any] = {}
            if "AuditorAgent" in self.agent_registry:
                audit_result = self._execute_agent_phase(
                    "AuditorAgent",
                    "audit_safety_checks",
                    {"workflow_trace": self.workflow_trace},
                )
                audit_data = audit_result.get("data", {})
                if not audit_data.get("audit_passed", True):
                    violations = audit_data.get("violations", [])
                    violation_summary = "; ".join(violations)
                    self.logger.critical(
                        f"POST-CYCLE AUDIT FAILED: {violation_summary}"
                    )
                    self.activate_circuit_breaker(f"Audit failed: {violation_summary}")

                try:
                    self.portfolio_cb.check(self._account_balance)
                except CircuitBreakTriggered as e:
                    self.activate_circuit_breaker(str(e))

            self._write_cycle_artifacts(cycle_results, audit_data, cycle_start)

    def _build_cycle_report(
        self, result: Dict[str, Any], stage_val: str, audit_data: Dict[str, Any], iso_ts: str,
    ) -> str:
        success = result.get("success", False) if isinstance(result, dict) else False
        audit_passed = audit_data.get("audit_passed", True) if audit_data else True
        violations = audit_data.get("violations", []) if audit_data else []
        return (
            f"# Cycle Report - {iso_ts}\n"
            f"- workflow: orchestrate_trading_workflow\n"
            f"- success: {success}\n"
            f"- stage: {stage_val}\n"
            f"- trading_paused: {self.trading_paused}\n"
            f"- circuit_breaker_active: {self.circuit_breaker_active}\n"
            f"- pause_reason: {self.pause_reason}\n"
            f"- audit_passed: {audit_passed}\n"
            f"- violations: {len(violations)}\n"
            f"- account_balance: {self._account_balance:.2f}\n"
            f"- next_task: wait_for_next_cycle\n"
        )

    def _write_cycle_report(self, cycle_md: str, ts: str) -> None:
        cycle_path = f"agent-logs/cycle-{ts}.md"
        try:
            with open(cycle_path, "w") as f:
                f.write(cycle_md)
        except Exception:
            logger.warning("Failed to write cycle report to %s", cycle_path)

    def _write_audit_trail(self, audit_data: Dict[str, Any], stage_val: str, iso_ts: str) -> None:
        violations = audit_data.get("violations", []) if audit_data else []
        audit_passed = audit_data.get("audit_passed", True) if audit_data else True
        trail_entry = {
            "timestamp": iso_ts,
            "audit_passed": audit_passed,
            "violation_count": len(violations),
            "violations": violations,
            "circuit_breaker_active": self.circuit_breaker_active,
            "stage": stage_val,
        }
        trail_path = "agent-logs/audit-trail.jsonl"
        try:
            with open(trail_path, "a") as f:
                f.write(json.dumps(trail_entry) + "\n")
        except Exception:
            logger.warning("Failed to append audit trail to %s", trail_path)

    def _write_return_report(
        self, result: Dict[str, Any], stage_val: str, audit_data: Dict[str, Any],
        cycle_start: float, ts: str, iso_ts: str,
    ) -> None:
        success = result.get("success", False) if isinstance(result, dict) else False
        violations = audit_data.get("violations", []) if audit_data else []
        audit_passed = audit_data.get("audit_passed", True) if audit_data else True
        duration = time.time() - cycle_start
        report = {
            "timestamp": iso_ts,
            "cycle_duration_seconds": round(duration, 2),
            "success": success,
            "stage": stage_val,
            "trading_paused": self.trading_paused,
            "circuit_breaker_active": self.circuit_breaker_active,
            "pause_reason": self.pause_reason,
            "audit_passed": audit_passed,
            "violations": violations,
            "account_balance": self._account_balance,
            "next_action": "wait_for_next_cycle",
        }
        report_path = f"agent-logs/return-report-{ts}.json"
        try:
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2)
        except Exception:
            logger.warning("Failed to write return report to %s", report_path)

    def _write_heartbeat_and_session(self, result: Dict[str, Any], iso_ts: str) -> None:
        success = result.get("success", False) if isinstance(result, dict) else False
        self._cycle_count += 1
        uptime = time.time() - self._start_time
        pid = os.getpid()
        heartbeat_status = "post-cycle" if success else "error"
        step = "post_cycle"

        heartbeat = {
            "timestamp": iso_ts,
            "pid": pid,
            "status": heartbeat_status,
            "step": step,
            "cycle": self._cycle_count,
            "mode": self.__class__.__name__,
            "uptime_seconds": round(uptime, 2),
        }
        try:
            with open(
                f"bot_heartbeat_{'dry_run' if self.is_paper_trading else 'live'}.json",
                "w",
            ) as f:
                json.dump(heartbeat, f)
        except Exception:
            logger.warning("Failed to write heartbeat file")

        session_state = {
            "lane": "kucoin-lane",
            "cycle": self._cycle_count,
            "timestamp": iso_ts,
            "mode": self.__class__.__name__,
            "executor_class": self.__class__.__name__,
            "status": heartbeat_status,
            "runtime_status": heartbeat_status,
            "phase": "active",
            "final": False,
            "step": step,
            "pid": pid,
            "uptime_seconds": round(uptime, 2),
        }
        if self.circuit_breaker_active or not success:
            session_state["error"] = self.pause_reason or "cycle_error"
        try:
            Path("lanes/kucoin/inbox").mkdir(parents=True, exist_ok=True)
            with open("lanes/kucoin/inbox/SESSION_STATE.json", "w") as f:
                json.dump(session_state, f)
        except Exception:
            logger.warning("Failed to write SESSION_STATE.json")

    def _write_cycle_artifacts(
        self,
        cycle_results: Dict[str, Any],
        audit_data: Dict[str, Any],
        cycle_start: float,
    ) -> None:
        os.makedirs("agent-logs", exist_ok=True)
        ts = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
        iso_ts = datetime.utcnow().isoformat()
        result = cycle_results.get("final_result", {})
        stage_val = self.current_stage.value

        cycle_md = self._build_cycle_report(result, stage_val, audit_data, iso_ts)
        self._write_cycle_report(cycle_md, ts)
        self._write_audit_trail(audit_data, stage_val, iso_ts)
        self._write_return_report(result, stage_val, audit_data, cycle_start, ts, iso_ts)
        self._write_heartbeat_and_session(result, iso_ts)

    def get_system_status(self) -> Dict[str, Any]:
        agent_statuses = [
            agent.get_status_report() for agent in self.agent_registry.values()
        ]
        return {
            "orchestrator": self.get_status_report(),
            "current_stage": self.current_stage.value,
            "trading_paused": self.trading_paused,
            "pause_reason": self.pause_reason,
            "circuit_breaker_active": self.circuit_breaker_active,
            "agents": agent_statuses,
            "workflow_history_length": len(self.workflow_history),
            "timestamp": datetime.utcnow().isoformat(),
        }
