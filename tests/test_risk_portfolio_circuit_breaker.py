import os
import json
import tempfile
import time
import pytest
from src.risk.portfolio_circuit_breaker import PortfolioCircuitBreaker, CircuitBreakTriggered


class TestPortfolioCircuitBreaker:
    @pytest.fixture
    def state_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield os.path.join(tmp, "state.json")

    @pytest.fixture
    def pcb(self, state_path):
        return PortfolioCircuitBreaker(
            starting_equity=10000.0,
            max_drawdown_pct=10.0,
            max_daily_loss_pct=6.0,
            cooldown_minutes=60,
            state_path=state_path,
        )

    def test_init(self, pcb):
        assert pcb.starting_equity == 10000.0
        assert pcb.max_drawdown_pct == 10.0
        assert pcb.tripped is False
        assert pcb.equity_peak == 10000.0

    def test_check_passes_with_normal_equity(self, pcb):
        pcb.check(10500.0)
        assert pcb.equity_peak == 10500.0
        assert pcb.tripped is False

    def test_check_trips_on_drawdown(self, pcb):
        pcb.check(10000.0)
        with pytest.raises(CircuitBreakTriggered, match="Drawdown"):
            pcb.check(8500.0)

    def test_check_trips_on_daily_loss(self, pcb):
        pcb.starting_equity = 10000.0
        pcb.max_daily_loss_pct = 5.0
        pcb.session_start_equity = 10000.0
        with pytest.raises(CircuitBreakTriggered, match="Daily loss"):
            pcb.check(9200.0)

    def test_check_raises_when_tripped(self, pcb):
        pcb.tripped = True
        pcb.trip_reason = "test"
        pcb.trip_time = time.time()
        pcb.cooldown_minutes = 1440
        with pytest.raises(CircuitBreakTriggered):
            pcb.check(10000.0)

    def test_check_auto_resets_after_cooldown(self, pcb):
        pcb.tripped = True
        pcb.trip_reason = "test"
        pcb.trip_time = time.time() - 7200
        pcb.cooldown_minutes = 60
        pcb.check(10000.0)
        assert pcb.tripped is False

    def test_reset(self, pcb):
        pcb.tripped = True
        pcb.trip_reason = "test"
        pcb.reset()
        assert pcb.tripped is False
        assert pcb.trip_reason == ""
        assert pcb.trip_time is None

    def test_starting_equity_clamped_to_zero(self, state_path):
        pcb = PortfolioCircuitBreaker(starting_equity=-100, state_path=state_path)
        assert pcb.starting_equity == 0
        assert pcb.equity_peak == 0

    def test_state_persists_and_loads(self, state_path):
        pcb1 = PortfolioCircuitBreaker(
            starting_equity=10000.0, max_drawdown_pct=10.0, max_daily_loss_pct=6.0,
            cooldown_minutes=60, state_path=state_path,
        )
        pcb1.check(11000.0)
        assert pcb1.equity_peak == 11000.0

        pcb2 = PortfolioCircuitBreaker(
            starting_equity=10000.0, max_drawdown_pct=10.0, max_daily_loss_pct=6.0,
            cooldown_minutes=60, state_path=state_path,
        )
        assert pcb2.equity_peak == 11000.0
