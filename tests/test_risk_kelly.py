import pytest
from src.risk.kelly_criterion import KellyPositionSizer


class TestKellyPositionSizer:
    @pytest.fixture
    def kelly(self):
        return KellyPositionSizer(
            min_position_pct=0.01,
            max_position_pct=0.25,
            min_trades_for_kelly=20,
            default_position_pct=0.10,
        )

    def test_init(self, kelly):
        assert kelly.min_position_pct == 0.01
        assert kelly.max_position_pct == 0.25
        assert kelly.min_trades_for_kelly == 20

    def test_calculate_metrics_empty_trades(self, kelly):
        metrics = kelly.calculate_metrics_from_trades([])
        assert metrics["win_rate"] == 0.5
        assert metrics["total_trades"] == 0

    def test_calculate_metrics_with_trades(self, kelly):
        trades = [
            {"pnl_pct": 5.0},
            {"pnl_pct": -3.0},
            {"pnl_pct": 2.0},
            {"pnl_pct": -1.0},
            {"pnl_pct": 4.0},
        ]
        metrics = kelly.calculate_metrics_from_trades(trades)
        assert metrics["total_trades"] == 5
        assert metrics["win_rate"] == 3 / 5
        assert metrics["avg_win"] > 0
        assert metrics["avg_loss"] > 0

    def test_calculate_kelly_pct_returns_default_below_min_trades(self, kelly):
        trades = [{"pnl_pct": 1.0}] * 5
        assert kelly.calculate_kelly_pct(trades) == 0.10

    def test_calculate_kelly_pct_with_sufficient_trades(self, kelly):
        trades = [{"pnl_pct": 5.0}] * 10 + [{"pnl_pct": -2.0}] * 10
        pct = kelly.calculate_kelly_pct(trades)
        assert kelly.min_position_pct <= pct <= kelly.max_position_pct

    def test_calculate_position_size_with_kelly(self, kelly):
        size = kelly.calculate_position_size(
            account_balance=10000.0,
            entry_price=100.0,
            kelly_pct=0.1,
        )
        expected = (10000.0 * 0.1) / 100.0
        assert size == pytest.approx(expected)

    def test_calculate_position_size_no_kelly_no_trades(self, kelly):
        size = kelly.calculate_position_size(
            account_balance=10000.0,
            entry_price=100.0,
        )
        expected = (10000.0 * 0.10) / 100.0
        assert size == pytest.approx(expected)

    def test_calculate_position_size_zero_entry(self, kelly):
        size = kelly.calculate_position_size(
            account_balance=10000.0,
            entry_price=0,
        )
        assert size == 0
