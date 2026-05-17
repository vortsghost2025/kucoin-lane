import time
import pytest
from collections import deque
from src.risk.circuit_breaker import CircuitBreaker


class TestCircuitBreaker:
    @pytest.fixture
    def cb(self):
        return CircuitBreaker(
            loss_threshold_pct=10.0,
            time_window_minutes=60,
            check_interval_seconds=0,
            name="TestCB",
        )

    def test_init(self, cb):
        assert cb.loss_threshold_pct == 10.0
        assert cb.is_tripped is False
        assert isinstance(cb.pnl_history, deque)
        assert len(cb.pnl_history) == 0

    def test_record_pnl(self, cb):
        cb.record_pnl(1000.0, 100.0)
        cb.record_pnl(900.0, 200.0)
        assert len(cb.pnl_history) == 2

    def test_record_pnl_prunes_old(self, cb):
        cb.time_window_minutes = 0
        cb.record_pnl(1000.0, 100.0)
        cb.record_pnl(900.0, 300.0)
        assert len(cb.pnl_history) <= 1

    def test_check_insufficient_data(self, cb):
        ok, reason = cb.check_circuit(1000.0, timestamp=100.0)
        assert ok is True
        assert "Insufficient data" in reason

    def test_check_healthy(self, cb):
        cb.check_circuit(1000.0, timestamp=100.0)
        ok, reason = cb.check_circuit(950.0, timestamp=200.0)
        assert ok is True
        assert "Healthy" in reason

    def test_check_trips_on_threshold(self, cb):
        cb.loss_threshold_pct = 5.0
        cb.check_circuit(1000.0, timestamp=100.0)
        ok, reason = cb.check_circuit(800.0, timestamp=200.0)
        assert ok is False
        assert "CIRCUIT BREAKER TRIPPED" in reason or "dropped" in reason

    def test_tripped_stays_tripped_during_cooldown(self, cb):
        cb.loss_threshold_pct = 5.0
        now = time.time()
        cb.check_circuit(1000.0, timestamp=now)
        cb.check_circuit(800.0, timestamp=now + 10)
        assert cb.is_tripped is True
        ok, reason = cb.check_circuit(1000.0, timestamp=now + 20)
        assert ok is False
        assert "cooldown" in reason.lower()

    def test_reset(self, cb):
        cb.is_tripped = True
        cb.trip_time = 100.0
        cb.trip_reason = "test"
        cb.pnl_history.append((1.0, 100.0))
        cb.reset()
        assert cb.is_tripped is False
        assert cb.trip_time is None
        assert len(cb.pnl_history) == 0
