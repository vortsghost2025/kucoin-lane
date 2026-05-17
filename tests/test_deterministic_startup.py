import os
import json
import tempfile
import pytest
from pathlib import Path
from src.deterministic_startup import DeterministicStartup


class TestDeterministicStartup:
    @pytest.fixture
    def workdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            yield Path(tmp)
            os.chdir(cwd)

    @pytest.fixture
    def startup(self):
        logs = []
        def diag(msg):
            logs.append(msg)
        s = DeterministicStartup(diag_log_func=diag)
        s._test_logs = logs
        return s

    def test_init(self, startup):
        assert startup.startup_path == []
        assert startup.verification_results == {}

    def test_log(self, startup):
        startup.log("hello")
        assert any("hello" in msg for msg in startup._test_logs)

    def test_cleanup_removes_stale_files(self, startup, workdir):
        (workdir / "bot_state.json").write_text("{}")
        (workdir / "bot_heartbeat.json").write_text("{}")
        result = startup.cleanup_leftover_state()
        assert result is True
        assert not (workdir / "bot_state.json").exists()
        assert not (workdir / "bot_heartbeat.json").exists()
        assert "cleanup_complete" in startup.startup_path

    def test_cleanup_no_files(self, startup, workdir):
        result = startup.cleanup_leftover_state()
        assert result is True

    def test_heartbeat_write_pass(self, startup, workdir):
        result = startup.test_heartbeat_write()
        assert result is True
        assert (workdir / "bot_heartbeat.json").exists()
        data = json.loads((workdir / "bot_heartbeat.json").read_text())
        assert data["test"] is True

    def test_heartbeat_write_corrupted_file(self, startup, workdir):
        (workdir / "bot_heartbeat.json").write_text("not json")
        result = startup.test_heartbeat_write()
        assert result is True

    def test_kucoin_api_no_client(self, startup):
        assert startup.test_kucoin_api(market_client=None) is True

    def test_working_directory_missing_env(self, startup, workdir):
        assert startup.test_working_directory() is False

    def test_working_directory_with_env(self, startup, workdir):
        (workdir / "requirements.txt").write_text("")
        os.environ["KUCOIN_API_KEY"] = "test"
        os.environ["KUCOIN_API_SECRET"] = "test"
        os.environ["KUCOIN_API_PASSPHRASE"] = "test"
        try:
            assert startup.test_working_directory() is True
        finally:
            del os.environ["KUCOIN_API_KEY"]
            del os.environ["KUCOIN_API_SECRET"]
            del os.environ["KUCOIN_API_PASSPHRASE"]

    def test_verify_critical_systems_default_fail(self, startup, workdir):
        result = startup.verify_critical_systems()
        assert result is False
        assert startup.verification_results.get("working_directory") is False

    def test_verify_critical_systems_pass(self, startup, workdir):
        (workdir / "requirements.txt").write_text("")
        os.environ["KUCOIN_API_KEY"] = "test"
        os.environ["KUCOIN_API_SECRET"] = "test"
        os.environ["KUCOIN_API_PASSPHRASE"] = "test"
        try:
            result = startup.verify_critical_systems(
                required_systems=["working_directory"]
            )
            assert result is True
            assert startup.verification_results.get("working_directory") is True
        finally:
            del os.environ["KUCOIN_API_KEY"]
            del os.environ["KUCOIN_API_SECRET"]
            del os.environ["KUCOIN_API_PASSPHRASE"]

    def test_get_startup_path(self, startup):
        startup.startup_path = ["a", "b", "c"]
        assert startup.get_startup_path() == "a -> b -> c"

    def test_log_startup_summary(self, startup):
        startup.startup_path = ["cleanup_started", "cleanup_complete"]
        startup.verification_results = {"heartbeat_io": True}
        startup.log_startup_summary()
        assert any("Startup path" in msg for msg in startup._test_logs)
