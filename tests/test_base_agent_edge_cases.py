import pytest
from src.base_agent import BaseAgent, AgentStatus


class ConcreteAgent(BaseAgent):
    def execute(self, input_data=None):
        self.log_execution_start("test_action")
        self.log_execution_end("test_action", success=True)
        return self.create_message(action="test_action", success=True)


class SlowAgent(BaseAgent):
    def execute(self, input_data=None):
        self.log_execution_start("slow_action")
        return self.create_message(action="slow_action", success=True)


class TestStatusTransitions:
    def test_idle_to_working_on_start(self):
        agent = ConcreteAgent("T1")
        assert agent.status == AgentStatus.IDLE
        agent.log_execution_start("act")
        assert agent.status == AgentStatus.WORKING

    def test_working_to_idle_on_success(self):
        agent = ConcreteAgent("T2")
        agent.log_execution_start("act")
        agent.log_execution_end("act", success=True)
        assert agent.status == AgentStatus.IDLE

    def test_working_to_error_on_failure(self):
        agent = ConcreteAgent("T3")
        agent.log_execution_start("act")
        agent.log_execution_end("act", success=False)
        assert agent.status == AgentStatus.ERROR

    def test_set_status_to_paused(self):
        agent = ConcreteAgent("T4")
        agent.set_status(AgentStatus.PAUSED)
        assert agent.status == AgentStatus.PAUSED

    def test_set_status_clears_error_when_no_error_arg(self):
        agent = ConcreteAgent("T5")
        agent.set_status(AgentStatus.ERROR, "boom")
        assert agent.last_error == "boom"
        agent.set_status(AgentStatus.IDLE)
        assert agent.last_error is None

    def test_set_status_preserves_error(self):
        agent = ConcreteAgent("T6")
        agent.set_status(AgentStatus.ERROR, "err1")
        agent.set_status(AgentStatus.ERROR, "err2")
        assert agent.last_error == "err2"

    def test_all_status_values(self):
        values = {s.value for s in AgentStatus}
        assert values == {"idle", "working", "error", "paused"}


class TestExecutionCountAndTiming:
    def test_execution_count_increments_on_success(self):
        agent = ConcreteAgent("T7")
        agent.execute()
        agent.execute()
        assert agent.execution_count == 2

    def test_execution_count_increments_on_failure(self):
        class FailAgent(BaseAgent):
            def execute(self, input_data=None):
                self.log_execution_start("act")
                self.log_execution_end("act", success=False)
                return {}

        agent = FailAgent("T8")
        agent.execute()
        assert agent.execution_count == 1
        assert agent.status == AgentStatus.ERROR

    def test_last_execution_time_updated(self):
        agent = ConcreteAgent("T9")
        assert agent.last_execution_time is None
        agent.execute()
        assert agent.last_execution_time is not None

    def test_double_execute_preserves_count(self):
        agent = ConcreteAgent("T10")
        agent.execute()
        agent.execute()
        assert agent.execution_count == 2

    def test_unfinished_execute_no_count_increment(self):
        agent = SlowAgent("T11")
        agent.execute()
        assert agent.execution_count == 0
        assert agent.status == AgentStatus.WORKING


class TestCreateMessage:
    def test_timestamp_is_iso_format(self):
        agent = ConcreteAgent("T12")
        msg = agent.create_message(action="test")
        from datetime import datetime
        datetime.fromisoformat(msg["timestamp"])

    def test_action_preserved(self):
        agent = ConcreteAgent("T13")
        msg = agent.create_message(action="custom_action")
        assert msg["action"] == "custom_action"

    def test_data_none_becomes_empty_dict(self):
        agent = ConcreteAgent("T14")
        msg = agent.create_message(action="test", data=None)
        assert msg["data"] == {}

    def test_error_default_none(self):
        agent = ConcreteAgent("T15")
        msg = agent.create_message(action="test", success=True)
        assert msg["error"] is None


class TestStatusReport:
    def test_status_report_string_values(self):
        agent = ConcreteAgent("T16")
        report = agent.get_status_report()
        assert isinstance(report["status"], str)
        assert isinstance(report["name"], str)

    def test_status_report_after_error(self):
        agent = ConcreteAgent("T17")
        agent.set_status(AgentStatus.ERROR, "fail")
        report = agent.get_status_report()
        assert report["status"] == "error"
        assert report["last_error"] == "fail"

    def test_status_report_execution_count_zero(self):
        agent = ConcreteAgent("T18")
        report = agent.get_status_report()
        assert report["execution_count"] == 0


class TestValidateInput:
    def test_validate_input_with_none_data(self):
        agent = ConcreteAgent("T19")
        valid, msg = agent.validate_input(None)
        assert valid is True

    def test_validate_input_with_empty_dict(self):
        agent = ConcreteAgent("T20")
        valid, msg = agent.validate_input({})
        assert valid is True


class TestLogging:
    def test_logger_name_matches_agent(self):
        agent = ConcreteAgent("MySpecialAgent")
        assert agent.logger.name == "MySpecialAgent"

    def test_setup_logging_idempotent(self):
        agent = ConcreteAgent("T21")
        initial_handlers = len(agent.logger.handlers)
        agent._setup_logging()
        assert len(agent.logger.handlers) == initial_handlers
