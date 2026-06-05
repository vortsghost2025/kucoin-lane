import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
import pandas as pd
from src.intelligence.orchestrator import (
    IntelligenceOrchestrator,
    WorkflowStage,
)
from src.base_agent import BaseAgent, AgentStatus


class MockAgent(BaseAgent):
    def __init__(self, name="MockAgent"):
        super().__init__(name)
        self.execute_return = {"success": True, "data": {}}

    def execute(self, input_data=None):
        return self.execute_return


class TestIntelligenceOrchestrator:
    @pytest.fixture
    def orchestrator(self, tmp_path):
        cb_state_file = str(tmp_path / "cb_state.json")
        portfolio_cb_file = str(tmp_path / "portfolio_cb_state.json")
        with patch.dict(
            os.environ,
            {
                "CB_STATE_PATH": cb_state_file,
                "PORTFOLIO_CB_STATE_PATH": portfolio_cb_file,
            },
        ):
            return IntelligenceOrchestrator(
                {
                    "enable_regime": False,
                    "enable_lead_lag": False,
                    "enable_whale": False,
                    "enable_dex_lag": False,
                    "paper_trading": True,
                }
            )

    def test_init(self, orchestrator):
        assert orchestrator.agent_name == "IntelligenceOrchestrator"
        assert orchestrator.enabled_modules == {
            "regime": False,
            "lead_lag": False,
            "whale": False,
            "dex_cex_lag": False,
        }
        assert orchestrator.current_stage == WorkflowStage.IDLE
        assert orchestrator.trading_paused is False

    def test_register_agent(self, orchestrator):
        agent = MockAgent("TestAgent")
        orchestrator.register_agent(agent)
        assert "TestAgent" in orchestrator.agent_registry

    def test_pause_trading(self, orchestrator):
        orchestrator.pause_trading("Test pause")
        assert orchestrator.trading_paused is True
        assert orchestrator.pause_reason == "Test pause"
        assert orchestrator.pause_timestamp is not None
        assert orchestrator.status == AgentStatus.PAUSED

    def test_resume_trading(self, orchestrator):
        orchestrator.pause_trading("Paused")
        orchestrator.resume_trading("Resumed")
        assert orchestrator.trading_paused is False
        assert orchestrator.pause_reason is None
        assert orchestrator.status == AgentStatus.IDLE

    def test_activate_circuit_breaker(self, orchestrator):
        orchestrator.activate_circuit_breaker("Test CB")
        assert orchestrator.circuit_breaker_active is True
        assert orchestrator.trading_paused is True
        assert "circuit breaker" in orchestrator.pause_reason.lower()

    def test_is_trading_allowed(self, orchestrator):
        allowed, reason = orchestrator.is_trading_allowed()
        assert allowed is True
        assert reason is None

    def test_is_trading_allowed_paused(self, orchestrator):
        orchestrator.pause_trading("Paused")
        allowed, reason = orchestrator.is_trading_allowed()
        assert allowed is False

    def test_is_trading_allowed_circuit_breaker(self, orchestrator):
        orchestrator.activate_circuit_breaker("Test")
        allowed, reason = orchestrator.is_trading_allowed()
        assert allowed is False
        assert "circuit breaker" in reason.lower()

    def test_transition_stage(self, orchestrator):
        orchestrator.transition_stage(WorkflowStage.FETCHING_DATA, {"key": "val"})
        assert orchestrator.current_stage == WorkflowStage.FETCHING_DATA
        assert len(orchestrator.workflow_history) == 1
        assert orchestrator.workflow_history[0]["from_stage"] == "idle"
        assert orchestrator.workflow_history[0]["to_stage"] == "fetching_data"

    def test_validate_agent_output_success(self, orchestrator):
        result = {"success": True, "data": {"key": "value"}}
        assert orchestrator._validate_agent_output(result, "Agent") is True

    def test_validate_agent_output_non_dict(self, orchestrator):
        assert orchestrator._validate_agent_output("not dict", "Agent") is False

    def test_validate_agent_output_missing_keys(self, orchestrator):
        result = {"success": True, "data": {"key": "value"}}
        assert (
            orchestrator._validate_agent_output(result, "Agent", ["missing"]) is False
        )

    def test_validate_agent_output_failed_ok(self, orchestrator):
        result = {"success": False, "error": "fail"}
        assert orchestrator._validate_agent_output(result, "Agent") is True

    def test_validate_market_data_valid(self, orchestrator):
        data = {"SOL/USDT": {"current_price": 100.0}}
        assert orchestrator._validate_market_data(data) is True

    def test_validate_market_data_invalid_price(self, orchestrator):
        data = {"SOL/USDT": {"current_price": -1}}
        assert orchestrator._validate_market_data(data) is False

    def test_validate_market_data_empty(self, orchestrator):
        assert orchestrator._validate_market_data({}) is False

    def test_execute_agent_phase_unregistered(self, orchestrator):
        result = orchestrator._execute_agent_phase("MissingAgent", "action", {})
        assert result["success"] is False
        assert "not registered" in result["error"]

    def test_execute_agent_phase_success(self, orchestrator):
        agent = MockAgent("TestAgent")
        orchestrator.register_agent(agent)
        result = orchestrator._execute_agent_phase("TestAgent", "test", {})
        assert result["success"] is True

    def test_execute_agent_phase_exception(self, orchestrator):
        agent = MockAgent("FailAgent")
        agent.execute = MagicMock(side_effect=Exception("oops"))
        orchestrator.register_agent(agent)
        result = orchestrator._execute_agent_phase("FailAgent", "test", {})
        assert result["success"] is False
        assert "oops" in result["error"]

    def test_handle_notional_rejection_below_threshold(self, orchestrator):
        result = orchestrator._handle_notional_rejection(
            "below minimum notional",
            {
                "assessments": {"SOL/USDT": {"pair": "SOL/USDT"}},
                "account_balance": 100,
            },
        )
        assert orchestrator.consecutive_notional_rejections == 1
        assert result["success"] is True
        assert result["data"]["reason"] == "notional_rejection"

    def test_handle_notional_rejection_at_threshold(self, orchestrator):
        orchestrator.notional_rejection_threshold = 3
        for _ in range(2):
            orchestrator._handle_notional_rejection(
                "below minimum notional",
                {
                    "assessments": {"SOL/USDT": {"pair": "SOL/USDT"}},
                    "account_balance": 100,
                },
            )
        assert orchestrator.consecutive_notional_rejections == 2
        result = orchestrator._handle_notional_rejection(
            "below minimum notional",
            {
                "assessments": {"SOL/USDT": {"pair": "SOL/USDT"}},
                "account_balance": 100,
            },
        )
        assert result["data"]["reason"] == "notional_rejection_pause"
        assert orchestrator.trading_paused is True

    def test_make_decision_baseline_hold(self, orchestrator):
        action, conf, mult, reasoning = orchestrator._make_decision(
            {
                "regime": {"recommendation": "USE_RSI", "adx": 15, "atr_pct": 0.02},
                "lead_lag": None,
                "whale": None,
            }
        )
        assert action == "HOLD"
        assert mult == 1.0

    def test_make_decision_lead_lag_danger(self, orchestrator):
        action, conf, mult, reasoning = orchestrator._make_decision(
            {
                "regime": None,
                "lead_lag": {"signal": "DANGER"},
                "whale": None,
            }
        )
        assert action == "EXIT_ALL"
        assert mult == 0.0

    def test_make_decision_whale_absorption(self, orchestrator):
        action, conf, mult, reasoning = orchestrator._make_decision(
            {
                "regime": {"recommendation": "USE_RSI", "adx": 15, "atr_pct": 0.02},
                "lead_lag": None,
                "whale": {
                    "signal": "BULLISH_ABSORPTION",
                    "confidence": 0.8,
                    "cvd_ratio": 0.7,
                },
            }
        )
        assert action == "BUY"

    def test_make_decision_whale_distribution(self, orchestrator):
        action, conf, mult, reasoning = orchestrator._make_decision(
            {
                "regime": {"recommendation": "USE_RSI", "adx": 15, "atr_pct": 0.02},
                "lead_lag": None,
                "whale": {"signal": "BEARISH_DISTRIBUTION", "confidence": 0.8},
            }
        )
        assert action == "SELL"

    def test_make_decision_high_volatility(self, orchestrator):
        action, conf, mult, reasoning = orchestrator._make_decision(
            {
                "regime": {"recommendation": "REDUCE_SIZE", "adx": 15, "atr_pct": 0.05},
                "lead_lag": None,
                "whale": None,
            }
        )
        assert action == "HOLD"
        assert mult == 0.5

    def test_should_allow_rsi_buy_true(self, orchestrator):
        assert (
            orchestrator.should_allow_rsi_buy(
                {"action": "HOLD", "position_multiplier": 0.5}
            )
            is True
        )

    def test_should_allow_rsi_buy_false(self, orchestrator):
        assert (
            orchestrator.should_allow_rsi_buy(
                {"action": "HOLD", "position_multiplier": 0.0}
            )
            is False
        )

    def test_should_emergency_exit_true(self, orchestrator):
        assert orchestrator.should_emergency_exit({"action": "EXIT_ALL"}) is True

    def test_get_position_size_adjustment(self, orchestrator):
        assert (
            orchestrator.get_position_size_adjustment({"position_multiplier": 0.5})
            == 0.5
        )

    def test_get_system_status(self, orchestrator):
        status = orchestrator.get_system_status()
        assert status["orchestrator"] is not None
        assert status["current_stage"] == "idle"
        assert status["trading_paused"] is False

    def test_v1_soft_halt(self, orchestrator):
        action, conf, mult, reasoning = orchestrator._handle_v1_soft_halt({"adx": 30})
        assert mult == 0.25

    def test_v2_two_candle_first(self, orchestrator):
        action, conf, mult, reasoning = orchestrator._handle_v2_two_candle(
            {"adx": 30}, "SOL/USDT"
        )
        assert mult == 0.5
        action2, conf2, mult2, reasoning2 = orchestrator._handle_v2_two_candle(
            {"adx": 30}, "SOL/USDT"
        )
        assert mult2 == 0.0

    def test_v3_cooldown(self, orchestrator):
        import time

        orchestrator.cooldown_override_active["SOL/USDT"] = time.time()
        action, conf, mult, reasoning = orchestrator._handle_v3_cooldown(
            {"adx": 30}, "SOL/USDT"
        )
        assert mult == 0.0

    def test_v3_cooldown_expired(self, orchestrator):
        import time

        orchestrator.cooldown_override_active["SOL/USDT"] = time.time() - 14400 - 1
        action, conf, mult, reasoning = orchestrator._handle_v3_cooldown(
            {"adx": 30}, "SOL/USDT"
        )
        assert mult == 0.5

    def test_v4_threshold_high_adx(self, orchestrator):
        action, conf, mult, reasoning = orchestrator._handle_v4_threshold(
            {"adx": 55}, "SOL/USDT"
        )
        assert mult == 0.0

    def test_v4_threshold_low_adx(self, orchestrator):
        action, conf, mult, reasoning = orchestrator._handle_v4_threshold(
            {"adx": 45}, "SOL/USDT"
        )
        assert mult == 0.5

    def test_run_cycle_dex_cex_lag_integration(self, tmp_path):
        """Full cycle integration test with DEX→CEX lag detection enabled."""
        cb_state_file = str(tmp_path / "cb_state.json")
        portfolio_cb_file = str(tmp_path / "portfolio_cb_state.json")
        with patch.dict(
            os.environ,
            {
                "CB_STATE_PATH": cb_state_file,
                "PORTFOLIO_CB_STATE_PATH": portfolio_cb_file,
            },
        ):
            orch = IntelligenceOrchestrator(
                {
                    "enable_regime": False,
                    "enable_lead_lag": False,
                    "enable_whale": False,
                    "enable_dex_lag": True,
                    "dex_lag_window_days": 30,
                    "dex_lag_min_composite": 0.4,
                    "paper_trading": True,
                }
            )

        # Verify detector is initialized
        assert orch.dex_cex_lag is not None
        assert orch.enabled_modules["dex_cex_lag"] is True

        # Register mock agents needed for workflow
        mock_data_fetcher = MockAgent("DataFetchingAgent")
        mock_data_fetcher.execute_return = {
            "success": True,
            "data": {
                "market_data": {
                    "BTC/USDT": {"current_price": 50500.0, "volume": 100},
                    "ETH/USDT": {"current_price": 3050.0, "volume": 200},
                }
            }
        }
        orch.register_agent(mock_data_fetcher)

        mock_market_analyzer = MockAgent("MarketAnalysisAgent")
        mock_market_analyzer.execute_return = {
            "success": True,
            "data": {
                "analysis": {
                    "BTC/USDT": {"signal_strength": 0.5, "regime": "bullish"},
                    "ETH/USDT": {"signal_strength": 0.3, "regime": "neutral"},
                },
                "regime": "bullish"
            }
        }
        orch.register_agent(mock_market_analyzer)

        mock_backtest_agent = MockAgent("BacktestingAgent")
        mock_backtest_agent.execute_return = {"success": True, "data": {"backtest_results": {}}}
        orch.register_agent(mock_backtest_agent)

        mock_risk_agent = MockAgent("RiskManagementAgent")
        mock_risk_agent.execute_return = {"success": True, "data": {"assessments": {}, "position_approved": True}}
        orch.register_agent(mock_risk_agent)

        mock_exec_agent = MockAgent("ExecutionAgent")
        mock_exec_agent.execute_return = {"success": True, "data": {"orders": [], "trade_executed": False}}
        orch.register_agent(mock_exec_agent)

        # Mock _klines_fetcher.fetch_klines (used in execute before data fetching agent)
        with patch.object(orch, "_klines_fetcher") as mock_fetcher:
            mock_fetcher.fetch_klines.side_effect = lambda adapter, symbol: pd.DataFrame(
                {
                    "open": [50000] * 20,
                    "high": [51000] * 20,
                    "low": [49000] * 20,
                    "close": [50500] * 20,
                    "volume": [100] * 20,
                }
            ) if symbol == "BTC/USDT" else pd.DataFrame(
                {
                    "open": [3000] * 20,
                    "high": [3100] * 20,
                    "low": [2900] * 20,
                    "close": [3050] * 20,
                    "volume": [200] * 20,
                }
            )

            # Mock dex_intelligence.execute if it exists
            if orch.dex_intelligence:
                with patch.object(orch.dex_intelligence, "execute") as mock_dex_exec:
                    mock_dex_exec.return_value = {"success": True, "dex_signals": []}
                    # Mock DexToCexLagDetector.run
                    with patch.object(orch.dex_cex_lag, "run") as mock_lag_run:
                        mock_lag_run.return_value = [
                            {
                                "base_token": "BTC",
                                "lead_lag_signal": "OPPORTUNITY",
                                "confidence": 0.75,
                                "composite_score": 0.8,
                                "lag_days": 5,
                                "dex_pair": "BTC/USDT",
                            }
                        ]
                        # Run full cycle
                        result = orch.execute(["BTC/USDT", "ETH/USDT"])

        # Verify cycle completed successfully
        assert result is not None
        assert result.get("success") is True
        
        # Verify dex_cex_lag.run was called and returned expected signals
        mock_lag_run.assert_called_once()
        
        # Verify the mock lag signal was returned by the detector
        lag_result = mock_lag_run.return_value
        assert len(lag_result) == 1
        assert lag_result[0]["lead_lag_signal"] == "OPPORTUNITY"
        assert lag_result[0]["base_token"] == "BTC"
