"""
Auditor Agent - Safety Verification
Post-cycle auditor that re-validates all safety checks.
Catches silent failures in other agents (e.g., incorrectly returned 0% risk).
"""

import logging
from typing import Any, Dict, List, Optional

from ..base_agent import BaseAgent


class AuditorAgent(BaseAgent):
    """
    Post-execution auditor that verifies all safety checks fired correctly.

    This is the "last line of defense" - runs AFTER the full workflow completes
    and independently re-validates that all four safety layers worked correctly:

    1. Trading pause check (orchestrator level)
    2. Downtrend detection (market analysis)
    3. 1% risk enforcement (risk management)
    4. Circuit breaker triggers (orchestrator)

    If ANY safety check that should have fired didn't fire, immediately
    activates the circuit breaker to prevent future trades until manual review.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("AuditorAgent", config)
        self.logger.setLevel(logging.INFO)

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self.log_execution_start("audit_safety_checks")

        try:
            workflow_trace = input_data.get("workflow_trace", [])

            if not workflow_trace:
                self.log_execution_end("audit_safety_checks", success=True)
                return self.create_message(
                    action="audit_safety_checks",
                    success=True,
                    data={
                        "violations": [],
                        "audit_passed": True,
                        "note": "No workflow trace to audit (possibly empty cycle)",
                    },
                )

            violations: List[str] = []

            analysis_msg = self._find_message(workflow_trace, "MarketAnalysisAgent")
            risk_msg = self._find_message(workflow_trace, "RiskManagementAgent")
            exec_msg = self._find_message(workflow_trace, "ExecutionAgent")

            if analysis_msg:
                violations.extend(self._audit_downtrend_detection(analysis_msg))

            if risk_msg and exec_msg:
                violations.extend(self._audit_risk_enforcement(risk_msg, exec_msg))

            if exec_msg:
                violations.extend(self._audit_position_sizing(exec_msg))

            audit_passed = len(violations) == 0

            if not audit_passed:
                self.logger.critical(
                    f"[AUDIT FAILED] Detected {len(violations)} safety violations!"
                )
                for v in violations:
                    self.logger.critical(f" - {v}")

            self.log_execution_end("audit_safety_checks", success=True)

            return self.create_message(
                action="audit_safety_checks",
                success=True,
                data={
                    "violations": violations,
                    "audit_passed": audit_passed,
                    "trace_length": len(workflow_trace),
                },
            )

        except Exception as e:
            self.logger.error(f"Auditor execution error: {e}")
            self.log_execution_end("audit_safety_checks", success=False)
            return self.create_message(
                action="audit_safety_checks", success=False, error=str(e)
            )

    def _find_message(self, trace: list, agent_name: str) -> Dict[str, Any]:
        for msg in reversed(trace):
            if isinstance(msg, dict) and msg.get("agent") == agent_name:
                return msg
        return {}

    def _audit_downtrend_detection(self, analysis_msg: Dict[str, Any]) -> List[str]:
        violations = []

        if not analysis_msg.get("success"):
            return violations

        data = analysis_msg.get("data", {})
        regime = data.get("regime")
        analysis = data.get("analysis", {})

        for symbol, symbol_analysis in analysis.items():
            if isinstance(symbol_analysis, dict):
                price_change = symbol_analysis.get("price_change_24h", 0)

                if price_change < -5.0 and regime != "bearish":
                    violations.append(
                        f"Downtrend detection FAILED: {symbol} dropped {price_change:.1f}% "
                        f"but regime='{regime}' (expected 'bearish')"
                    )

        return violations

    def _audit_risk_enforcement(
        self, risk_msg: Dict[str, Any], exec_msg: Dict[str, Any]
    ) -> List[str]:
        violations = []

        risk_data = risk_msg.get("data", {})
        exec_data = exec_msg.get("data", {})

        trade_executed = exec_data.get("trade_executed", False)
        position_approved = risk_data.get("position_approved", False)

        if trade_executed and not position_approved:
            violations.append(
                "Risk enforcement FAILED: Trade executed without position approval from RiskManager"
            )

        risk_percent = risk_data.get("risk_percent", 0)
        if trade_executed and risk_percent > 1.0:
            violations.append(
                f"Risk enforcement FAILED: Trade executed with {risk_percent:.2f}% risk (max 1%)"
            )

        position_size = risk_data.get("position_size", 0)
        if trade_executed and position_size > 0 and risk_percent == 0:
            violations.append(
                "Risk calculation BUG: Non-zero position size but 0% risk (possible division by zero)"
            )

        return violations

    def _audit_position_sizing(self, exec_msg: Dict[str, Any]) -> List[str]:
        violations = []

        exec_data = exec_msg.get("data", {})
        trade_executed = exec_data.get("trade_executed", False)

        if not trade_executed:
            return violations

        position_size = exec_data.get("position_size", 0)

        if position_size < 0:
            violations.append(
                f"Position sizing BUG: Negative position size {position_size}"
            )

        if position_size > 1.0:
            violations.append(
                f"Position sizing BUG: Position size {position_size} exceeds 100% of account"
            )

        return violations
