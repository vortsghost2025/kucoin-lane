import pytest
from src.risk.risk_manager import RiskManagementAgent, MAX_DAILY_LOSS_CAP


class TestRiskManagementAgent:
    @pytest.fixture
    def config(self):
        return {
            "account_balance": 10000.0,
            "risk_per_trade": 0.01,
            "min_risk_reward_ratio": 1.5,
            "max_daily_loss": 0.05,
            "default_stop_loss_pct": 0.02,
            "min_signal_strength": 0.3,
            "min_win_rate": 0.45,
            "min_notional_usd": 0.50,
            "min_position_size_units": 0.01,
            "enforce_min_position_size_only": True,
            "min_position_size_by_pair": {
                "SOL/USDT": 0.01,
                "BTC/USDT": 0.0001,
                "ETH/USDT": 0.001,
            },
        }

    @pytest.fixture
    def agent(self, config):
        return RiskManagementAgent(config)

    def test_init(self, agent):
        assert agent.agent_name == "RiskManagementAgent"
        assert agent.account_balance == 10000.0
        assert agent.max_daily_loss <= MAX_DAILY_LOSS_CAP
        assert agent.cumulative_risk_today == 0.0

    def test_execute_missing_data(self, agent):
        result = agent.execute({"market_data": {}, "analysis": {}})
        assert result["success"] is False

    def test_execute_valid_trade(self, agent):
        result = agent.execute({
            "market_data": {
                "SOL/USDT": {"current_price": 100.0},
                "BTC/USDT": {"current_price": 50000.0},
            },
            "analysis": {
                "SOL/USDT": {
                    "signal_strength": 0.8,
                    "volatility_approved": True,
                    "entry_timing_approved": True,
                    "regime": "bullish",
                },
            },
            "backtest_results": {
                "SOL/USDT": {"win_rate": 0.6},
            },
        })
        assert result["success"] is True
        data = result["data"]
        assert data["position_approved"] is True
        assert data["position_size"] > 0

    def test_execute_with_unconfigured_min_size(self, agent):
        agent.enforce_min_position_size_only = True
        agent.min_position_size_by_pair = {}
        agent.min_position_size_units = 0
        result = agent.execute({
            "market_data": {
                "SOL/USDT": {"current_price": 100.0},
            },
            "analysis": {
                "SOL/USDT": {
                    "signal_strength": 0.8,
                    "volatility_approved": True,
                    "entry_timing_approved": True,
                    "regime": "bullish",
                },
            },
            "backtest_results": {
                "SOL/USDT": {"win_rate": 0.6},
            },
        })
        assert result["data"]["position_approved"] is False

    def test_execute_exceeds_notional(self, agent):
        agent.min_position_size_by_pair = {"SOL/USDT": 1000.0}
        result = agent.execute({
            "market_data": {
                "SOL/USDT": {"current_price": 100.0},
            },
            "analysis": {
                "SOL/USDT": {
                    "signal_strength": 0.8,
                    "volatility_approved": True,
                    "entry_timing_approved": True,
                    "regime": "bullish",
                },
            },
            "backtest_results": {
                "SOL/USDT": {"win_rate": 0.6},
            },
        })
        data = result["data"]
        assert data["position_approved"] is False

    def test_reset_daily_risk(self, agent):
        agent.cumulative_risk_today = 50.0
        agent.reset_daily_risk()
        assert agent.cumulative_risk_today == 0.0

    def test_update_account_balance(self, agent):
        agent.update_account_balance(20000.0)
        assert agent.account_balance == 20000.0

    def test_max_daily_loss_capped(self, config):
        config["max_daily_loss"] = 0.50
        agent = RiskManagementAgent(config)
        assert agent.max_daily_loss <= MAX_DAILY_LOSS_CAP
