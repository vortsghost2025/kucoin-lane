import pytest
from src.intelligence.backtester import BacktestingAgent


class TestBacktestingAgent:
    @pytest.fixture
    def config(self):
        return {
            "min_win_rate": 0.45,
            "max_drawdown": 0.15,
        }

    @pytest.fixture
    def agent(self, config):
        return BacktestingAgent(config)

    def test_init(self, agent):
        assert agent.agent_name == "BacktestingAgent"
        assert agent.min_backtest_win_rate == 0.45

    def test_execute_missing_data(self, agent):
        result = agent.execute({"market_data": {}, "analysis": {}})
        assert result["success"] is False

    def test_execute_valid(self, agent):
        result = agent.execute({
            "market_data": {"SOL/USDT": {"current_price": 100.0}},
            "analysis": {
                "SOL/USDT": {
                    "recommendation": "BUY",
                    "signal_strength": 0.8,
                }
            },
        })
        assert result["success"] is True
        data = result["data"]
        assert "backtest_results" in data
        assert "all_signals_valid" in data
        sol_result = data["backtest_results"]["SOL/USDT"]
        assert sol_result["pair"] == "SOL/USDT"

    def test_calculate_buy_signal_win_rate(self, agent):
        wr = agent._calculate_buy_signal_win_rate(0.5, "SOL/USDT")
        assert 0 <= wr <= 0.75

    def test_calculate_sell_signal_win_rate(self, agent):
        wr = agent._calculate_sell_signal_win_rate(0.5, "SOL/USDT")
        assert 0 <= wr <= 0.65

    def test_estimate_max_drawdown_buy(self, agent):
        dd = agent._estimate_max_drawdown("BUY", 0.5, "SOL/USDT")
        assert dd >= 0.02

    def test_estimate_max_drawdown_sell(self, agent):
        dd = agent._estimate_max_drawdown("SELL", 0.5, "SOL/USDT")
        assert dd >= 0.02

    def test_estimate_max_drawdown_hold(self, agent):
        dd = agent._estimate_max_drawdown("HOLD", 0, "SOL/USDT")
        assert dd >= 0.02

    def test_get_validation_reason_valid(self, agent):
        reason = agent._get_validation_reason(True, 0.6, 0.08)
        assert "passed" in reason.lower()

    def test_get_validation_reason_invalid(self, agent):
        reason = agent._get_validation_reason(False, 0.3, 0.20)
        assert "below" in reason or "exceeds" in reason

    def test_get_validation_reason_both_fail(self, agent):
        reason = agent._get_validation_reason(False, 0.3, 0.30)
        assert ";" in reason

    def test_add_historical_data(self, agent):
        agent.add_historical_data("SOL/USDT", {"price": 100.0})
        assert agent.historical_data["SOL/USDT"] == {"price": 100.0}
