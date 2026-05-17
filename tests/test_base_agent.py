import pytest
from datetime import datetime
from src.base_agent import BaseAgent, AgentStatus


class ConcreteAgent(BaseAgent):
    def execute(self, input_data=None):
        self.log_execution_start("test_action")
        self.log_execution_end("test_action", success=True)
        return self.create_message(action="test_action", success=True, data={"result": "ok"})


class FailingAgent(BaseAgent):
    def execute(self, input_data=None):
        self.log_execution_start("fail_action")
        self.set_status(AgentStatus.ERROR, "Something went wrong")
        self.log_execution_end("fail_action", success=False)
        return self.create_message(action="fail_action", success=False, error="Something went wrong")


class TestBaseAgent:
    def test_init(self):
        agent = ConcreteAgent("TestAgent", {"key": "value"})
        assert agent.agent_name == "TestAgent"
        assert agent.config == {"key": "value"}
        assert agent.status == AgentStatus.IDLE
        assert agent.last_error is None
        assert agent.execution_count == 0

    def test_init_no_config(self):
        agent = ConcreteAgent("TestAgent")
        assert agent.config == {}
        assert agent.agent_name == "TestAgent"

    def test_set_status_idle(self):
        agent = ConcreteAgent("TestAgent")
        agent.set_status(AgentStatus.WORKING)
        assert agent.status == AgentStatus.WORKING
        assert agent.last_error is None

    def test_set_status_error(self):
        agent = ConcreteAgent("TestAgent")
        agent.set_status(AgentStatus.ERROR, "error msg")
        assert agent.status == AgentStatus.ERROR
        assert agent.last_error == "error msg"

    def test_create_message_defaults(self):
        agent = ConcreteAgent("TestAgent")
        msg = agent.create_message(action="some_action")
        assert msg["agent"] == "TestAgent"
        assert msg["action"] == "some_action"
        assert msg["success"] is True
        assert msg["data"] == {}
        assert msg["error"] is None
        assert "timestamp" in msg

    def test_create_message_custom(self):
        agent = ConcreteAgent("TestAgent")
        msg = agent.create_message(action="test", data={"x": 1}, success=False, error="fail")
        assert msg["data"] == {"x": 1}
        assert msg["success"] is False
        assert msg["error"] == "fail"

    def test_execute_not_implemented(self):
        agent = BaseAgent("AbstractAgent")
        with pytest.raises(NotImplementedError):
            agent.execute()

    def test_validate_input_default(self):
        agent = ConcreteAgent("TestAgent")
        valid, msg = agent.validate_input({"foo": "bar"})
        assert valid is True
        assert msg is None

    def test_get_status_report(self):
        agent = ConcreteAgent("TestAgent")
        report = agent.get_status_report()
        assert report["name"] == "TestAgent"
        assert report["status"] == "idle"
        assert report["execution_count"] == 0
        assert report["last_execution_time"] is None
        assert report["last_error"] is None

    def test_log_execution_start_sets_working(self):
        agent = ConcreteAgent("TestAgent")
        agent.log_execution_start("my_action")
        assert agent.status == AgentStatus.WORKING

    def test_log_execution_end_success(self):
        agent = ConcreteAgent("TestAgent")
        agent.log_execution_start("act")
        agent.log_execution_end("act", success=True)
        assert agent.status == AgentStatus.IDLE
        assert agent.execution_count == 1
        assert agent.last_execution_time is not None

    def test_log_execution_end_failure(self):
        agent = ConcreteAgent("TestAgent")
        agent.log_execution_start("act")
        agent.log_execution_end("act", success=False)
        assert agent.status == AgentStatus.ERROR
        assert agent.execution_count == 1

    def test_concrete_execute(self):
        agent = ConcreteAgent("TestAgent")
        result = agent.execute()
        assert result["success"] is True
        assert result["data"]["result"] == "ok"
        assert agent.execution_count == 1

    def test_failing_agent_execute(self):
        agent = FailingAgent("FailAgent")
        result = agent.execute()
        assert result["success"] is False
        assert result["error"] == "Something went wrong"
        assert agent.status == AgentStatus.ERROR

    def test_get_status_report_after_execution(self):
        agent = ConcreteAgent("TestAgent")
        agent.execute()
        report = agent.get_status_report()
        assert report["execution_count"] == 1
        assert report["last_execution_time"] is not None

    def test_setup_logging_adds_handler(self):
        agent = ConcreteAgent("LogTestAgent")
        assert len(agent.logger.handlers) >= 1
