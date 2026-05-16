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
import logging
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import pandas as pd

from ..base_agent import BaseAgent, AgentStatus
from ..config import REGIME_GUARD_MODE
from .regime_detector import RegimeDetector
from .lead_lag import LeadLagMonitor
from .whale_watch import WhaleWatch

logger = logging.getLogger(__name__)


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
        self.circuit_breaker_active = False
        self.agent_registry: Dict[str, BaseAgent] = {}
        self.is_paper_trading = config.get("paper_trading", True)
        self._last_daily_reset: Optional[str] = None

        self.consecutive_notional_rejections = 0
        self.notional_rejection_threshold = config.get(
            "notional_rejection_threshold", 10
        )
        self.notional_pause_duration_hours = config.get(
            "notional_pause_duration_hours", 1.0
        )

        self.logger.setLevel(logging.DEBUG)
        self.logger.info(
            f"IntelligenceOrchestrator initialized: {self.enabled_modules}"
        )
        self.logger.info(f"Regime Guard Mode: {self.regime_guard_mode}")

    def register_agent(self, agent: BaseAgent) -> None:
        self.agent_registry[agent.agent_name] = agent
        self.logger.info(f"Registered agent: {agent.agent_name}")

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
        self.logger.critical(f"[CRITICAL] CIRCUIT BREAKER ACTIVATED: {reason}")

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
                f"RECOMMENDATION: Increase account balance to $500+ or adjust risk parameters. "
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
                    "recommendation": "Increase account balance to $500+ or adjust risk parameters",
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
        risk_agent = self.agent_registry.get("RiskManagementAgent")
        if risk_agent and hasattr(risk_agent, "update_account_balance"):
            risk_agent.update_account_balance(float(new_balance))
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
                1.0,
                0.0,
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
                        0.9,
                        0.0,
                        f"TRENDING_DOWN detected (ADX: {regime['adx']:.1f}), no longs",
                    )

            if results["whale"] and regime["recommendation"] == "USE_RSI":
                whale = results["whale"]

                if (
                    whale["signal"] == "BULLISH_ABSORPTION"
                    and whale["confidence"] > 0.6
                ):
                    return (
                        "BUY",
                        0.95,
                        1.0,
                        f"STRONG SIGNAL: Ranging market + Whale absorption "
                        f"(CVD: {whale['cvd_ratio']:.1%})",
                    )

                elif whale["signal"] == "BEARISH_DISTRIBUTION":
                    return ("SELL", 0.8, 0.0, "Whales distributing, exit positions")

            if regime["recommendation"] == "REDUCE_SIZE":
                return (
                    "HOLD",
                    0.5,
                    0.5,
                    f"High volatility regime (ATR: {regime['atr_pct']:.2f}%), "
                    f"reduced position sizing",
                )

            elif regime["recommendation"] == "USE_RSI":
                return (
                    "HOLD",
                    0.7,
                    1.0,
                    f"Ranging market (ADX: {regime['adx']:.1f}), RSI strategy approved",
                )

        return (
            "HOLD",
            0.3,
            0.8,
            "No strong intelligence signal, proceeding with caution",
        )

    def _handle_v1_soft_halt(self, regime: Dict) -> tuple:
        return (
            "HOLD",
            0.7,
            0.25,
            f"V1_SOFT_HALT: Downtrend detected (ADX: {regime['adx']:.1f}), "
            f"reduced to 25% position size for probe trades",
        )

    def _handle_v2_two_candle(self, regime: Dict, symbol: str) -> tuple:
        if symbol is None:
            symbol = "UNKNOWN"

        self.consecutive_downtrend_count[symbol] = (
            self.consecutive_downtrend_count.get(symbol, 0) + 1
        )

        if self.consecutive_downtrend_count[symbol] >= 2:
            return (
                "HOLD",
                0.9,
                0.0,
                f"V2_TWO_CANDLE: {self.consecutive_downtrend_count[symbol]} consecutive "
                f"TRENDING_DOWN signals (ADX: {regime['adx']:.1f}), halting",
            )
        else:
            return (
                "HOLD",
                0.6,
                0.5,
                f"V2_TWO_CANDLE: 1st downtrend signal ({self.consecutive_downtrend_count[symbol]}/2), "
                f"probing with 50% position size",
            )

    def _handle_v3_cooldown(self, regime: Dict, symbol: str) -> tuple:
        if symbol is None:
            symbol = "UNKNOWN"

        current_time = time.time()
        last_low_time = self.cooldown_override_active.get(symbol, current_time)
        cooldown_hours = 4
        cooldown_seconds = cooldown_hours * 3600

        if current_time - last_low_time > cooldown_seconds:
            return (
                "HOLD",
                0.6,
                0.5,
                f"V3_COOLDOWN: {cooldown_hours}h since last low, probing with 50% position size "
                f"(ADX: {regime['adx']:.1f})",
            )
        else:
            hours_left = (cooldown_seconds - (current_time - last_low_time)) / 3600
            return (
                "HOLD",
                0.9,
                0.0,
                f"V3_COOLDOWN: Cooldown active ({hours_left:.1f}h remaining), "
                f"no trades until recovery confirmed (ADX: {regime['adx']:.1f})",
            )

    def _handle_v4_threshold(self, regime: Dict, symbol: str) -> tuple:
        adx = regime.get("adx", 0)

        if adx > 50:
            return (
                "HOLD",
                0.9,
                0.0,
                f"V4_THRESHOLD: Strong downtrend (ADX: {adx:.1f} > 50), halting",
            )
        else:
            return (
                "HOLD",
                0.6,
                0.5,
                f"V4_THRESHOLD: Mild downtrend (ADX: {adx:.1f} < 50), "
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
            elif not self._validate_agent_output(
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

            if market_regime == "bearish" and not self.trading_paused:
                self.pause_trading(
                    "Bearish market regime detected - downtrend protection active"
                )
                cycle_results["final_result"] = self.create_message(
                    action="orchestrate_workflow",
                    success=True,
                    data={"trading_paused": True, "reason": "bearish_regime"},
                )
                return cycle_results["final_result"]

            if self.trading_paused:
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
            elif not self._validate_agent_output(
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
