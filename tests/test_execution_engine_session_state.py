import json
import os
from pathlib import Path

import pytest

from src.execution import execution_engine as execution_engine_module
from src.execution.execution_engine import ExecutionEngine


REPO_ROOT = Path(__file__).resolve().parents[1]
LANE_RELAY = json.loads((REPO_ROOT / "governance" / "lane-relay.json").read_text())
SESSION_STATE_REL_PATH = Path(LANE_RELAY["session_state"]["path"])
LANE_NAME = LANE_RELAY["lane"]


class SingleSuccessCycleEngine(ExecutionEngine):
    def run_cycle(self):
        self.is_running = False


class SingleErrorCycleEngine(ExecutionEngine):
    def run_cycle(self):
        self.is_running = False
        raise RuntimeError("forced cycle failure")


@pytest.fixture
def isolated_lane_workspace(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    (tmp_path / SESSION_STATE_REL_PATH).parent.mkdir(parents=True, exist_ok=True)
    try:
        yield tmp_path
    finally:
        os.chdir(original_cwd)


@pytest.fixture(autouse=True)
def mute_telegram(monkeypatch):
    monkeypatch.setattr(
        execution_engine_module, "send_telegram_notification", lambda _msg: True
    )


def _load_session_state(workspace: Path) -> dict:
    state_path = workspace / SESSION_STATE_REL_PATH
    assert state_path.exists(), (
        "SESSION_STATE.json must be emitted at "
        f"'{SESSION_STATE_REL_PATH.as_posix()}' per lane-relay contract"
    )
    return json.loads(state_path.read_text(encoding="utf-8"))


def test_session_state_written_after_successful_cycle(isolated_lane_workspace):
    engine = SingleSuccessCycleEngine(config={})

    engine.run_continuous(interval_minutes=0)

    session_state = _load_session_state(isolated_lane_workspace)
    assert session_state["lane"] == LANE_NAME
    assert session_state["cycle"] >= 1
    assert session_state["timestamp"]
    assert session_state["mode"] == engine.__class__.__name__
    assert session_state["status"]


def test_session_state_contains_minimum_contract_fields(isolated_lane_workspace):
    engine = SingleSuccessCycleEngine(config={})

    engine.run_continuous(interval_minutes=0)

    session_state = _load_session_state(isolated_lane_workspace)
    required_fields = ["lane", "cycle", "timestamp", "mode", "status", "phase", "final"]
    for field in required_fields:
        assert field in session_state, f"Missing required SESSION_STATE field: {field}"
    assert isinstance(session_state["phase"], str)
    assert isinstance(session_state["final"], bool)
    assert session_state["phase"] in {
        "booting",
        "active",
        "standby",
        "fault",
        "terminating",
        "unknown",
    }


def test_session_state_updates_with_error_status_after_cycle_exception(
    isolated_lane_workspace,
):
    engine = SingleErrorCycleEngine(config={})

    engine.run_continuous(interval_minutes=0)

    session_state = _load_session_state(isolated_lane_workspace)
    assert session_state["lane"] == LANE_NAME
    assert session_state["cycle"] >= 1
    assert session_state["status"] == "error"
    assert session_state["mode"] == engine.__class__.__name__


def test_session_state_records_shutdown_final_status(isolated_lane_workspace):
    engine = SingleSuccessCycleEngine(config={})
    engine.cycle_count = 7

    engine.shutdown()

    session_state = _load_session_state(isolated_lane_workspace)
    assert session_state["lane"] == LANE_NAME
    assert session_state["cycle"] == 7
    assert session_state["mode"] == engine.__class__.__name__
    assert session_state["status"] in {"shutdown", "final"}
    assert session_state["final"] is True
    assert session_state["phase"] == "terminating"

    last = engine._last_runtime_status
    assert last in {"shutdown", "final"}
