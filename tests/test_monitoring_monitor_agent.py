import os
import json
import pytest
import tempfile
from unittest.mock import patch, MagicMock
from src.monitoring.monitor_agent import MonitoringAgent


class TestMonitoringAgent:
    @pytest.fixture
    def config(self):
        return {"logs_dir": tempfile.mkdtemp()}

    @pytest.fixture
    def agent(self, config):
        agent = MonitoringAgent(config)
        yield agent

    def test_init(self, agent):
        assert agent.agent_name == "MonitoringAgent"
        assert agent.events_count == 0
        assert agent.alerts == []

    def test_init_creates_dir(self):
        test_dir = tempfile.mkdtemp()
        agent = MonitoringAgent({"logs_dir": test_dir})
        assert os.path.exists(test_dir)

    def test_execute_logs_event(self, agent):
        result = agent.execute({
            "workflow_stage": "monitoring",
            "data_result": {"success": True},
            "analysis_result": {"success": True},
            "risk_result": {"success": True, "data": {"position_approved": True}},
            "exec_result": {"success": True, "data": {"trade_executed": False}},
        })
        assert result["success"] is True
        assert agent.events_count == 1
        assert result["data"]["events_logged"] == 1

    def test_generate_alerts_trade_executed(self, agent):
        event = {
            "execution": {
                "success": True,
                "data": {
                    "trade_executed": True,
                    "trade_id": 1,
                    "entry_price": 100.0,
                    "position_size": 0.5,
                },
            },
            "risk_assessment": {"success": True, "data": {"position_approved": True}},
            "market_analysis": {"success": True, "data": {"downtrend_detected": False}},
        }
        alerts = agent._generate_alerts(event)
        assert len(alerts) == 1
        assert alerts[0]["level"] == "INFO"
        assert "Trade #1 executed" in alerts[0]["message"]

    def test_generate_alerts_trade_rejected(self, agent):
        event = {
            "execution": {"success": True, "data": {"trade_executed": False}},
            "risk_assessment": {
                "success": True,
                "data": {"position_approved": False, "rejection_reason": "Risk limit exceeded"},
            },
            "market_analysis": {"success": True, "data": {"downtrend_detected": False}},
        }
        alerts = agent._generate_alerts(event)
        assert len(alerts) == 1
        assert alerts[0]["level"] == "WARNING"
        assert "rejected" in alerts[0]["message"].lower()

    def test_generate_alerts_downtrend_detected(self, agent):
        event = {
            "execution": {"success": True, "data": {"trade_executed": False}},
            "risk_assessment": {"success": True, "data": {"position_approved": True}},
            "market_analysis": {"success": True, "data": {"downtrend_detected": True}},
        }
        alerts = agent._generate_alerts(event)
        assert len(alerts) == 1
        assert alerts[0]["level"] == "WARNING"
        assert "downtrend" in alerts[0]["message"].lower()

    def test_generate_alerts_multiple(self, agent):
        event = {
            "execution": {
                "success": True,
                "data": {"trade_executed": True, "trade_id": 1, "entry_price": 100.0, "position_size": 0.5},
            },
            "risk_assessment": {
                "success": True,
                "data": {"position_approved": False, "rejection_reason": "Risk limit"},
            },
            "market_analysis": {"success": True, "data": {"downtrend_detected": True}},
        }
        alerts = agent._generate_alerts(event)
        assert len(alerts) >= 2

    def test_get_alerts_no_filter(self, agent):
        agent.alerts = [
            {"level": "INFO", "message": "test1"},
            {"level": "WARNING", "message": "test2"},
        ]
        result = agent.get_alerts()
        assert len(result) == 2

    def test_get_alerts_with_filter(self, agent):
        agent.alerts = [
            {"level": "INFO", "message": "test1"},
            {"level": "WARNING", "message": "test2"},
        ]
        result = agent.get_alerts(level="WARNING")
        assert len(result) == 1
        assert result[0]["message"] == "test2"

    def test_clear_alerts(self, agent):
        agent.alerts.append({"level": "INFO", "message": "test"})
        agent.clear_alerts()
        assert agent.alerts == []

    def test_export_event_log(self, agent):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"event": 1}) + "\n")
            f.write(json.dumps({"event": 2}) + "\n")
            agent.events_log = f.name
        events = agent.export_event_log(limit=1)
        assert len(events) == 1
        assert events[0]["event"] == 2

    def test_export_event_log_no_file(self, agent):
        agent.events_log = os.path.join(tempfile.gettempdir(), "nonexistent_events.jsonl")
        events = agent.export_event_log()
        assert events == []
