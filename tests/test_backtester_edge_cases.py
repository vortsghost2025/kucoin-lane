import pytest
from src.intelligence.backtester import BacktestingAgent


class TestBacktesterBoundaryWinRates:
    @pytest.fixture
    def agent(self):
        return BacktestingAgent({"min_win_rate": 0.45, "max_drawdown": 0.15})

    def test_zero_signal_strength_buy(self, agent):
        wr = agent._calculate_buy_signal_win_rate(0.0, "SOL/USDT")
        assert wr == pytest.approx(0.52, abs=0.01)

    def test_max_signal_strength_buy(self, agent):
        wr = agent._calculate_buy_signal_win_rate(1.0, "SOL/USDT")
        assert wr <= 0.75

    def test_zero_signal_strength_sell(self, agent):
        wr = agent._calculate_sell_signal_win_rate(0.0, "SOL/USDT")
        assert wr == pytest.approx(0.48, abs=0.01)

    def test_max_signal_strength_sell(self, agent):
        wr = agent._calculate_sell_signal_win_rate(1.0, "SOL/USDT")
        assert wr <= 0.65

    def test_btc_lower_win_rate_than_sol(self, agent):
        sol_wr = agent._calculate_buy_signal_win_rate(0.5, "SOL/USDT")
        btc_wr = agent._calculate_buy_signal_win_rate(0.5, "BTC/USDT")
        assert btc_wr < sol_wr

    def test_eth_lower_win_rate_than_sol(self, agent):
        sol_wr = agent._calculate_buy_signal_win_rate(0.5, "SOL/USDT")
        eth_wr = agent._calculate_buy_signal_win_rate(0.5, "ETH/USDT")
        assert eth_wr < sol_wr

    def test_unknown_pair_falls_back_to_sol(self, agent):
        unknown_wr = agent._calculate_buy_signal_win_rate(0.5, "DOGE/USDT")
        sol_wr = agent._calculate_buy_signal_win_rate(0.5, "SOL/USDT")
        assert unknown_wr == sol_wr


class TestBacktesterDrawdownBoundary:
    @pytest.fixture
    def agent(self):
        return BacktestingAgent({"min_win_rate": 0.45, "max_drawdown": 0.15})

    def test_hold_drawdown_less_than_buy(self, agent):
        hold_dd = agent._estimate_max_drawdown("HOLD", 0.5, "SOL/USDT")
        buy_dd = agent._estimate_max_drawdown("BUY", 0.5, "SOL/USDT")
        assert hold_dd < buy_dd

    def test_sell_drawdown_greater_than_buy(self, agent):
        buy_dd = agent._estimate_max_drawdown("BUY", 0.5, "SOL/USDT")
        sell_dd = agent._estimate_max_drawdown("SELL", 0.5, "SOL/USDT")
        assert sell_dd > buy_dd

    def test_higher_strength_lower_drawdown(self, agent):
        low_dd = agent._estimate_max_drawdown("BUY", 0.2, "SOL/USDT")
        high_dd = agent._estimate_max_drawdown("BUY", 0.8, "SOL/USDT")
        assert high_dd < low_dd

    def test_drawdown_floored_at_002(self, agent):
        dd = agent._estimate_max_drawdown("BUY", 1.0, "SOL/USDT")
        assert dd >= 0.02

    def test_btc_higher_drawdown_than_sol(self, agent):
        sol_dd = agent._estimate_max_drawdown("BUY", 0.5, "SOL/USDT")
        btc_dd = agent._estimate_max_drawdown("BUY", 0.5, "BTC/USDT")
        assert btc_dd > sol_dd


class TestBacktesterValidation:
    @pytest.fixture
    def agent(self):
        return BacktestingAgent({"min_win_rate": 0.45, "max_drawdown": 0.15})

    def test_strong_buy_signal_is_valid(self, agent):
        result = agent.execute({
            "market_data": {"SOL/USDT": {"current_price": 100.0}},
            "analysis": {"SOL/USDT": {"recommendation": "BUY", "signal_strength": 0.9}},
        })
        assert result["success"] is True
        sol = result["data"]["backtest_results"]["SOL/USDT"]
        assert sol["signal_valid"] is True
        assert sol["recommendation"] == "PROCEED"

    def test_hold_signal_low_drawdown_valid(self, agent):
        result = agent.execute({
            "market_data": {"SOL/USDT": {"current_price": 100.0}},
            "analysis": {"SOL/USDT": {"recommendation": "HOLD", "signal_strength": 0}},
        })
        sol = result["data"]["backtest_results"]["SOL/USDT"]
        assert sol["win_rate"] == 0.5
        assert sol["max_drawdown"] < 0.15
        assert sol["signal_valid"] is True

    def test_weak_sell_on_btc_invalid(self, agent):
        result = agent.execute({
            "market_data": {"BTC/USDT": {"current_price": 60000}},
            "analysis": {"BTC/USDT": {"recommendation": "SELL", "signal_strength": 0.1}},
        })
        btc = result["data"]["backtest_results"]["BTC/USDT"]
        assert btc["signal_valid"] is False

    def test_empty_market_data_fails(self, agent):
        result = agent.execute({"market_data": {}, "analysis": {}})
        assert result["success"] is False

    def test_none_input_data_fails(self, agent):
        result = agent.execute({})
        assert result["success"] is False

    def test_multiple_pairs_all_valid(self, agent):
        result = agent.execute({
            "market_data": {
                "SOL/USDT": {"current_price": 100},
                "ETH/USDT": {"current_price": 3000},
            },
            "analysis": {
                "SOL/USDT": {"recommendation": "BUY", "signal_strength": 0.9},
                "ETH/USDT": {"recommendation": "BUY", "signal_strength": 0.9},
            },
        })
        assert result["success"] is True
        assert result["data"]["all_signals_valid"] is True
        assert result["data"]["pairs_analyzed"] == 2

    def test_average_win_rate_computed(self, agent):
        result = agent.execute({
            "market_data": {"SOL/USDT": {"current_price": 100}},
            "analysis": {"SOL/USDT": {"recommendation": "BUY", "signal_strength": 0.5}},
        })
        assert result["data"]["average_win_rate"] > 0

    def test_validation_reason_on_fail(self, agent):
        reason = agent._get_validation_reason(False, 0.3, 0.25)
        assert "below" in reason.lower() or "exceeds" in reason.lower()

    def test_validation_reason_both_fail(self, agent):
        reason = agent._get_validation_reason(False, 0.3, 0.30)
        assert ";" in reason


class TestBacktesterConfig:
    def test_none_config_uses_defaults(self):
        agent = BacktestingAgent(None)
        assert agent.min_backtest_win_rate == 0.45
        assert agent.max_drawdown_allowed == 0.15

    def test_empty_config_uses_defaults(self):
        agent = BacktestingAgent({})
        assert agent.min_backtest_win_rate == 0.45

    def test_custom_config(self):
        agent = BacktestingAgent({"min_win_rate": 0.6, "max_drawdown": 0.1})
        assert agent.min_backtest_win_rate == 0.6
        assert agent.max_drawdown_allowed == 0.1

    def test_add_historical_data_stores(self):
        agent = BacktestingAgent(None)
        agent.add_historical_data("DOGE/USDT", {"price": 0.1})
        assert agent.historical_data["DOGE/USDT"] == {"price": 0.1}

    def test_add_historical_data_overwrites(self):
        agent = BacktestingAgent(None)
        agent.add_historical_data("DOGE/USDT", {"price": 0.1})
        agent.add_historical_data("DOGE/USDT", {"price": 0.2})
        assert agent.historical_data["DOGE/USDT"] == {"price": 0.2}
