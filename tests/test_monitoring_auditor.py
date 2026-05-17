import pytest
from src.monitoring.auditor import AuditorAgent


class TestAuditorAgent:
    @pytest.fixture
    def auditor(self):
        return AuditorAgent({"key": "value"})

    def test_init(self, auditor):
        assert auditor.agent_name == "AuditorAgent"
        assert auditor.config == {"key": "value"}

    def test_execute_empty_trace(self, auditor):
        result = auditor.execute({"workflow_trace": []})
        assert result["success"] is True
        assert result["data"]["audit_passed"] is True

    def test_execute_no_trace_key(self, auditor):
        result = auditor.execute({})
        assert result["success"] is True
        assert result["data"]["audit_passed"] is True

    def test_find_message(self, auditor):
        trace = [
            {"agent": "OtherAgent", "success": True, "data": {}},
            {"agent": "TargetAgent", "success": True, "data": {"key": "val"}},
        ]
        found = auditor._find_message(trace, "TargetAgent")
        assert found["agent"] == "TargetAgent"
        assert found["data"]["key"] == "val"

    def test_find_message_not_found(self, auditor):
        assert auditor._find_message([], "MissingAgent") == {}

    def test_audit_downtrend_detection_ok(self, auditor):
        msg = {
            "success": True,
            "data": {
                "regime": "bearish",
                "analysis": {
                    "SOL/USDT": {"price_change_24h": -6.0},
                },
            },
        }
        violations = auditor._audit_downtrend_detection(msg)
        assert len(violations) == 0

    def test_audit_downtrend_detection_fail(self, auditor):
        msg = {
            "success": True,
            "data": {
                "regime": "bullish",
                "analysis": {
                    "SOL/USDT": {"price_change_24h": -6.0},
                },
            },
        }
        violations = auditor._audit_downtrend_detection(msg)
        assert len(violations) == 1
        assert "Downtrend detection FAILED" in violations[0]

    def test_audit_risk_enforcement_trade_without_approval(self, auditor):
        violations = auditor._audit_risk_enforcement(
            {"success": True, "data": {"position_approved": False, "risk_percent": 0.5, "position_size": 0}},
            {"success": True, "data": {"trade_executed": True}},
        )
        assert len(violations) == 1
        assert "executed without position approval" in violations[0]

    def test_audit_risk_enforcement_over_1pct(self, auditor):
        violations = auditor._audit_risk_enforcement(
            {"success": True, "data": {"position_approved": True, "risk_percent": 2.0, "position_size": 1.0}},
            {"success": True, "data": {"trade_executed": True}},
        )
        assert any("risk" in v.lower() for v in violations)

    def test_audit_risk_enforcement_zero_risk_bug(self, auditor):
        violations = auditor._audit_risk_enforcement(
            {"success": True, "data": {"position_approved": True, "risk_percent": 0, "position_size": 1.0}},
            {"success": True, "data": {"trade_executed": True}},
        )
        assert any("0%" in v for v in violations)

    def test_audit_position_sizing_negative(self, auditor):
        msg = {"success": True, "data": {"trade_executed": True, "position_size": -1.0}}
        violations = auditor._audit_position_sizing(msg)
        assert len(violations) == 1
        assert "negative" in violations[0].lower()

    def test_audit_position_sizing_too_large(self, auditor):
        msg = {"success": True, "data": {"trade_executed": True, "position_size": 1.5}}
        violations = auditor._audit_position_sizing(msg)
        assert len(violations) == 1
        assert "100%" in violations[0]

    def test_audit_position_sizing_not_executed(self, auditor):
        msg = {"success": True, "data": {"trade_executed": False, "position_size": 0}}
        violations = auditor._audit_position_sizing(msg)
        assert len(violations) == 0

    def test_full_audit_passes(self, auditor):
        analysis_msg = {
            "agent": "MarketAnalysisAgent", "success": True,
            "data": {"regime": "bullish", "analysis": {"SOL/USDT": {"price_change_24h": 2.0}}},
        }
        risk_msg = {
            "agent": "RiskManagementAgent", "success": True,
            "data": {"position_approved": True, "risk_percent": 0.5, "position_size": 1.0},
        }
        exec_msg = {
            "agent": "ExecutionAgent", "success": True,
            "data": {"trade_executed": True, "position_size": 0.5},
        }
        result = auditor.execute({
            "workflow_trace": [analysis_msg, risk_msg, exec_msg],
        })
        assert result["success"] is True
        assert result["data"]["audit_passed"] is True
