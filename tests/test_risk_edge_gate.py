import pytest
from src.risk.edge_gate import EdgeGate, EdgeGateResult


class TestEdgeGateResult:
    def test_approved(self):
        r = EdgeGateResult(True, "", fee_pct=0.20, expected_edge_pct=1.0)
        assert r.approved is True
        assert r.rejection_reason == ""
        assert r.fee_pct == 0.20
        assert r.expected_edge_pct == 1.0

    def test_rejected(self):
        r = EdgeGateResult(False, "bad", total_friction_pct=0.50)
        assert r.approved is False
        assert r.rejection_reason == "bad"
        assert r.total_friction_pct == 0.50

    def test_defaults(self):
        r = EdgeGateResult(True)
        assert r.fee_pct == 0.0
        assert r.spread_pct == 0.0
        assert r.slippage_pct == 0.0
        assert r.safety_margin_pct == 0.0
        assert r.total_friction_pct == 0.0
        assert r.expected_edge_pct == 0.0
        assert r.expected_profit_usd == 0.0


class TestEdgeGate:
    @pytest.fixture
    def gate(self):
        return EdgeGate()

    @pytest.fixture
    def tight_gate(self):
        return EdgeGate({
            "round_trip_fee_pct": 0.20,
            "slippage_pct": 0.05,
            "safety_margin_pct": 0.10,
            "min_profit_usd": 0.25,
            "max_spread_pct": 1.0,
            "min_edge_pct": 0.40,
            "min_notional_usd": 5.0,
            "max_trade_loss_usd": 1.10,
        })

    def test_defaults(self, gate):
        assert gate.round_trip_fee_pct == 0.20
        assert gate.slippage_pct == 0.05
        assert gate.safety_margin_pct == 0.10
        assert gate.min_profit_usd == 0.25
        assert gate.max_spread_pct == 1.0
        assert gate.min_edge_pct == 0.40
        assert gate.min_notional_usd == 5.0
        assert gate.max_trade_loss_usd == 1.10

    def test_approve_healthy_trade(self, gate):
        result = gate.evaluate(
            expected_edge_pct=1.5,
            position_size_usd=55.0,
            spread_pct=0.10,
            stop_loss_pct=2.0,
            pair="BTC/USDT",
        )
        assert result.approved is True
        assert result.rejection_reason == ""
        assert result.total_friction_pct == pytest.approx(0.45, abs=0.01)
        assert result.expected_profit_usd == pytest.approx(0.825, abs=0.01)

    def test_reject_below_min_notional(self, gate):
        result = gate.evaluate(
            expected_edge_pct=5.0,
            position_size_usd=3.0,
            pair="BTC/USDT",
        )
        assert result.approved is False
        assert "below minimum" in result.rejection_reason

    def test_reject_spread_too_wide(self, gate):
        result = gate.evaluate(
            expected_edge_pct=2.0,
            position_size_usd=55.0,
            spread_pct=1.5,
            pair="DOGE/USDT",
        )
        assert result.approved is False
        assert "Spread" in result.rejection_reason

    def test_reject_edge_below_friction(self, gate):
        result = gate.evaluate(
            expected_edge_pct=0.30,
            position_size_usd=55.0,
            spread_pct=0.0,
            pair="ETH/USDT",
        )
        assert result.approved is False
        assert "friction" in result.rejection_reason.lower()

    def test_reject_edge_below_min_edge(self, gate):
        result = gate.evaluate(
            expected_edge_pct=0.38,
            position_size_usd=55.0,
            spread_pct=0.0,
            pair="ETH/USDT",
        )
        total_friction = gate.round_trip_fee_pct + gate.slippage_pct + gate.safety_margin_pct
        assert total_friction == 0.35
        assert result.expected_edge_pct >= total_friction
        assert result.approved is False
        assert "below minimum" in result.rejection_reason

    def test_reject_profit_below_min(self, gate):
        result = gate.evaluate(
            expected_edge_pct=0.50,
            position_size_usd=5.0,
            spread_pct=0.0,
            pair="BTC/USDT",
        )
        assert result.expected_profit_usd == pytest.approx(0.025, abs=0.001)
        assert result.approved is False
        assert "profit" in result.rejection_reason.lower()

    def test_reject_loss_exceeds_max(self, gate):
        result = gate.evaluate(
            expected_edge_pct=1.5,
            position_size_usd=110.0,
            spread_pct=0.0,
            stop_loss_pct=5.0,
            pair="BTC/USDT",
        )
        assert result.approved is False
        assert "loss" in result.rejection_reason.lower()

    def test_approve_at_min_notional(self, gate):
        result = gate.evaluate(
            expected_edge_pct=5.0,
            position_size_usd=5.0,
            spread_pct=0.0,
            pair="BTC/USDT",
        )
        assert result.approved is True

    def test_friction_calculation(self, gate):
        result = gate.evaluate(
            expected_edge_pct=2.0,
            position_size_usd=55.0,
            spread_pct=0.15,
            pair="BTC/USDT",
        )
        expected_friction = 0.20 + 0.15 + 0.05 + 0.10
        assert result.total_friction_pct == pytest.approx(expected_friction, abs=0.01)

    def test_zero_stop_loss_no_loss_rejection(self, gate):
        result = gate.evaluate(
            expected_edge_pct=2.0,
            position_size_usd=110.0,
            spread_pct=0.0,
            stop_loss_pct=0.0,
            pair="BTC/USDT",
        )
        assert result.approved is True

    def test_custom_config(self):
        custom = EdgeGate({
            "round_trip_fee_pct": 0.10,
            "slippage_pct": 0.02,
            "safety_margin_pct": 0.05,
            "min_profit_usd": 0.10,
            "max_spread_pct": 0.5,
            "min_edge_pct": 0.20,
            "min_notional_usd": 1.0,
            "max_trade_loss_usd": 0.50,
        })
        assert custom.round_trip_fee_pct == 0.10
        assert custom.min_notional_usd == 1.0

    def test_evaluate_take_profit_delegates(self, gate):
        result = gate.evaluate_take_profit(
            take_profit_pct=2.5,
            position_size_usd=55.0,
            spread_pct=0.10,
            pair="BTC/USDT",
        )
        assert result.approved is True
        assert result.expected_edge_pct == 2.5

    def test_evaluate_take_profit_rejects(self, gate):
        result = gate.evaluate_take_profit(
            take_profit_pct=0.20,
            position_size_usd=55.0,
            pair="BTC/USDT",
        )
        assert result.approved is False

    def test_micro_account_btc_scenario(self, tight_gate):
        result = tight_gate.evaluate(
            expected_edge_pct=2.4,
            position_size_usd=50.0,
            spread_pct=0.02,
            stop_loss_pct=2.0,
            pair="BTC/USDT",
        )
        assert result.approved is True
        assert result.expected_profit_usd == pytest.approx(1.20, abs=0.01)

    def test_micro_account_eth_scenario(self, tight_gate):
        result = tight_gate.evaluate(
            expected_edge_pct=1.0,
            position_size_usd=50.0,
            spread_pct=0.05,
            stop_loss_pct=1.5,
            pair="ETH/USDT",
        )
        assert result.approved is True
        assert result.expected_profit_usd == pytest.approx(0.50, abs=0.01)

    def test_reject_tiny_edge_at_110_capital(self, tight_gate):
        result = tight_gate.evaluate(
            expected_edge_pct=0.35,
            position_size_usd=55.0,
            spread_pct=0.0,
            pair="BTC/USDT",
        )
        assert result.approved is False
