import pytest
from unittest.mock import patch, MagicMock
from src.execution.execution_engine import DryRunExecutor
from src.risk.risk_manager import RiskManagementAgent


class TestDryRunExecutorCrossPairFix:
    @pytest.fixture
    def config(self):
        return {"max_open_positions": 3, "max_trades_per_session": 5}

    @patch.object(DryRunExecutor, "load_backtest_data")
    def test_uses_pair_from_input_data(self, mock_load, config):
        executor = DryRunExecutor(config)
        market_data = {
            "BTC/USDT": {"current_price": 73415.0},
            "ETH/USDT": {"current_price": 1984.0},
        }
        result = executor.execute({
            "market_data": market_data,
            "pair": "ETH/USDT",
            "position_size": 0.005,
            "stop_loss": 1936.0,
            "take_profit": 2041.0,
        })
        assert result["success"] is True
        assert result["data"]["trade_executed"] is True
        assert result["data"]["pair"] == "ETH/USDT"
        assert result["data"]["entry_price"] == 1984.0
        assert len(executor.open_positions) == 1
        assert executor.open_positions[0]["pair"] == "ETH/USDT"
        assert executor.open_positions[0]["entry_price"] == 1984.0

    @patch.object(DryRunExecutor, "load_backtest_data")
    def test_falls_back_to_first_key_without_pair(self, mock_load, config):
        executor = DryRunExecutor(config)
        market_data = {
            "BTC/USDT": {"current_price": 73415.0},
            "ETH/USDT": {"current_price": 1984.0},
        }
        result = executor.execute({
            "market_data": market_data,
            "position_size": 0.0001,
            "stop_loss": 72000.0,
            "take_profit": 75000.0,
        })
        assert result["success"] is True
        assert result["data"]["trade_executed"] is True
        assert result["data"]["pair"] == "BTC/USDT"
        assert result["data"]["entry_price"] == 73415.0

    @patch.object(DryRunExecutor, "load_backtest_data")
    def test_pair_not_in_market_data_uses_safe_fallback(self, mock_load, config):
        executor = DryRunExecutor(config)
        market_data = {
            "BTC/USDT": {"current_price": 73415.0},
            "ETH/USDT": {"current_price": 1984.0},
        }
        result = executor.execute({
            "market_data": market_data,
            "pair": "SOL/USDT",
            "position_size": 0.1,
            "stop_loss": 140.0,
            "take_profit": 160.0,
        })
        assert result["success"] is True
        assert result["data"]["trade_executed"] is True
        assert result["data"]["pair"] == "SOL/USDT"

    @patch.object(DryRunExecutor, "load_backtest_data")
    def test_notional_uses_correct_pair_price(self, mock_load, config):
        executor = DryRunExecutor(config)
        market_data = {
            "BTC/USDT": {"current_price": 73415.0},
            "ETH/USDT": {"current_price": 1984.0},
        }
        eth_size = 0.005
        result = executor.execute({
            "market_data": market_data,
            "pair": "ETH/USDT",
            "position_size": eth_size,
            "stop_loss": 1936.0,
            "take_profit": 2041.0,
        })
        expected_notional = eth_size * 1984.0
        assert result["data"]["entry_value"] == pytest.approx(expected_notional, rel=1e-6)
        wrong_notional = eth_size * 73415.0
        assert result["data"]["entry_value"] < wrong_notional


class TestRiskManagerCrossPairOutput:
    @pytest.fixture
    def config(self):
        return {
            "account_balance": 110.0,
            "risk_per_trade": 0.01,
            "min_risk_reward_ratio": 1.2,
            "max_daily_loss": 0.03,
            "default_stop_loss_pct": 0.02,
            "min_signal_strength": 0.3,
            "min_win_rate": 0.45,
            "min_notional_usd": 1.0,
            "min_position_size_units": 0.001,
            "enforce_min_position_size_only": False,
            "min_position_size_by_pair": {
                "BTC/USDT": 0.00001,
                "ETH/USDT": 0.0001,
            },
        }

    @pytest.fixture
    def agent(self, config):
        return RiskManagementAgent(config)

    def test_approved_pair_emitted_in_data(self, agent):
        result = agent.execute({
            "market_data": {
                "BTC/USDT": {"current_price": 73415.0},
                "ETH/USDT": {"current_price": 1984.0},
            },
            "analysis": {
                "BTC/USDT": {
                    "signal_strength": 0.1,
                    "volatility_approved": False,
                    "entry_timing_approved": False,
                    "regime": "ranging",
                },
                "ETH/USDT": {
                    "signal_strength": 0.8,
                    "volatility_approved": True,
                    "entry_timing_approved": True,
                    "regime": "bullish",
                    "recommendation": "BUY",
                },
            },
            "backtest_results": {
                "BTC/USDT": {"win_rate": 0.3},
                "ETH/USDT": {"win_rate": 0.6},
            },
        })
        assert result["success"] is True
        data = result["data"]
        assert data["position_approved"] is True
        assert data["pair"] == "ETH/USDT"
        assert data["position_size"] > 0
        assert data["current_price"] == 1984.0
        assert data["stop_loss"] is not None
        assert data["stop_loss"] < 1984.0
        assert data["take_profit"] is not None
        assert data["take_profit"] > 1984.0

    def test_no_approved_pair_returns_none(self, agent):
        result = agent.execute({
            "market_data": {
                "BTC/USDT": {"current_price": 73415.0},
                "ETH/USDT": {"current_price": 1984.0},
            },
            "analysis": {
                "BTC/USDT": {
                    "signal_strength": 0.1,
                    "volatility_approved": False,
                    "entry_timing_approved": False,
                    "regime": "ranging",
                },
                "ETH/USDT": {
                    "signal_strength": 0.1,
                    "volatility_approved": False,
                    "entry_timing_approved": False,
                    "regime": "ranging",
                },
            },
            "backtest_results": {},
        })
        assert result["success"] is True
        data = result["data"]
        assert data["position_approved"] is False
        assert data["pair"] is None
        assert data["position_size"] == 0

    def test_sl_tp_match_approved_pair_not_first_pair(self, agent):
        result = agent.execute({
            "market_data": {
                "BTC/USDT": {"current_price": 73415.0},
                "ETH/USDT": {"current_price": 1984.0},
            },
            "analysis": {
                "BTC/USDT": {
                    "signal_strength": 0.1,
                    "volatility_approved": False,
                    "entry_timing_approved": False,
                    "regime": "ranging",
                },
                "ETH/USDT": {
                    "signal_strength": 0.7,
                    "volatility_approved": True,
                    "entry_timing_approved": True,
                    "regime": "bullish",
                    "recommendation": "BUY",
                },
            },
            "backtest_results": {
                "ETH/USDT": {"win_rate": 0.55},
            },
        })
        data = result["data"]
        sl = data["stop_loss"]
        tp = data["take_profit"]
        assert sl is not None and sl > 0
        assert tp is not None and tp > 0
        eth_price = 1984.0
        assert abs(sl - eth_price) < 500, f"SL {sl} is far from ETH price {eth_price} — looks like BTC SL applied to ETH"
        assert abs(tp - eth_price) < 500, f"TP {tp} is far from ETH price {eth_price} — looks like BTC TP applied to ETH"
