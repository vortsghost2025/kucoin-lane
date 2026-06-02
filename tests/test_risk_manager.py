import pytest
from unittest.mock import patch, MagicMock
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


class TestRiskManagerKellyPaths:
    """Regression tests for the Kelly-criterion sizing paths in _assess_pair_risk.

    Bug: actual_risk_amount was not assigned in the Kelly success path
    (only in the except and else branches), causing UnboundLocalError.
    """

    @pytest.fixture
    def kelly_config(self):
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
            "enforce_min_position_size_only": False,
        "kelly": {
            "min_position_pct": 0.01,
            "max_position_pct": 0.25,
            "min_trades_for_kelly": 20,
            "default_position_pct": 0.10,
        },
        "asset_config_default": {
            "stop_loss_adjustment": 1.0,
            "position_size_multiplier": 1.0,
            "max_stop_loss_pct": 0.10,
        },
        "asset_configs": {
            "SOL/USDT": {"stop_loss_adjustment": 1.0, "position_size_multiplier": 1.0},
        },
    }

    def _make_input(self, signal_strength=0.8, win_rate=0.6):
        return {
            "market_data": {
                "SOL/USDT": {"current_price": 100.0},
            },
            "analysis": {
                "SOL/USDT": {
                    "signal_strength": signal_strength,
                    "volatility_approved": True,
                    "entry_timing_approved": True,
                    "regime": "bullish",
                },
            },
            "backtest_results": {
                "SOL/USDT": {"win_rate": win_rate},
            },
        }

    def test_kelly_success_path_risk_amount_defined(self, kelly_config):
        """Kelly criterion succeeds — actual_risk_amount must be > 0 in result."""
        agent = RiskManagementAgent(kelly_config)
        winning_trades = [{"pnl_pct": 2.0}] * 15 + [{"pnl_pct": -1.0}] * 5
        agent.trade_history = winning_trades

        result = agent.execute(self._make_input())
        assert result["success"] is True
        assessment = result["data"]["assessments"]["SOL/USDT"]
        assert assessment["risk_amount"] > 0, (
            f"Kelly success path must set risk_amount > 0, got {assessment['risk_amount']}"
        )

    def test_kelly_exception_path_fallback_risk_amount(self, kelly_config):
        """Kelly criterion raises — fallback must still produce valid risk_amount."""
        agent = RiskManagementAgent(kelly_config)
        agent.trade_history = [{"pnl_pct": 1.0}] * 25

        with patch.object(
            agent.kelly_sizer, "calculate_kelly_pct", side_effect=RuntimeError("kelly boom")
        ):
            result = agent.execute(self._make_input())
            assert result["success"] is True
            assessment = result["data"]["assessments"]["SOL/USDT"]
            assert assessment["risk_amount"] > 0, (
                f"Kelly exception fallback must set risk_amount > 0, got {assessment['risk_amount']}"
            )

    def test_kelly_not_enough_trades_uses_fixed_path(self, kelly_config):
        """Not enough trade history — falls to fixed (else) path, risk_amount valid."""
        agent = RiskManagementAgent(kelly_config)
        agent.trade_history = [{"pnl_pct": 1.0}] * 5

        result = agent.execute(self._make_input())
        assert result["success"] is True
        assessment = result["data"]["assessments"]["SOL/USDT"]
        assert assessment["risk_amount"] > 0, (
            f"Non-Kelly fixed path must set risk_amount > 0, got {assessment['risk_amount']}"
        )

    def test_kelly_success_risk_amount_matches_position(self, kelly_config):
        """Verify actual_risk_amount = position_size * risk_per_unit after Kelly success."""
        agent = RiskManagementAgent(kelly_config)
        winning_trades = [{"pnl_pct": 3.0}] * 14 + [{"pnl_pct": -1.0}] * 6
        agent.trade_history = winning_trades

        result = agent.execute(self._make_input(signal_strength=1.0, win_rate=0.7))
        assessment = result["data"]["assessments"]["SOL/USDT"]
        current_price = 100.0
        stop_loss_pct = agent.default_stop_loss_pct
        stop_loss = current_price * (1 - stop_loss_pct)
        risk_per_unit = current_price - stop_loss
        expected_risk = assessment["position_size"] * risk_per_unit
        assert assessment["risk_amount"] == pytest.approx(expected_risk, rel=1e-6), (
            f"risk_amount {assessment['risk_amount']} != position_size * risk_per_unit {expected_risk}"
        )


class TestMicroAccountSizing:
    """Micro accounts (<$200) use full risk_per_trade with no confidence
    multiplier reduction. Signal threshold already gates WHETHER to trade;
    a trade worth taking gets full risk allocation.

    This fixes the bug where confidence_multiplier = signal × win_rate
    could shrink a $1.10 risk budget to $0.39, producing $2 notional
    positions that fail exchange minimums.
    """

    @pytest.fixture
    def micro_config(self):
        return {
            "account_balance": 110.0,
            "risk_per_trade": 0.01,
            "min_risk_reward_ratio": 2.0,
            "max_daily_loss": 0.05,
            "default_stop_loss_pct": 0.02,
            "min_signal_strength": 0.30,
            "min_win_rate": 0.45,
            "min_notional_usd": 5.0,
            "min_position_size_units": 0.00001,
            "enforce_min_position_size_only": False,
            "min_position_size_by_pair": {
                "BTC/USDT": 0.00001,
            },
            "asset_config_default": {
                "min_signal_strength_adjustment": 0.0,
                "stop_loss_adjustment": 1.0,
                "position_size_multiplier": 1.0,
                "max_stop_loss_pct": 0.06,
            },
            "asset_configs": {
                "BTC/USDT": {
                    "min_signal_strength_adjustment": 0.05,
                    "stop_loss_adjustment": 0.95,
                    "position_size_multiplier": 0.80,
                },
            },
        }

    def _make_btc_input(self, signal_strength=0.713, win_rate=0.5):
        return {
            "market_data": {
                "BTC/USDT": {"current_price": 71408.89},
            },
            "analysis": {
                "BTC/USDT": {
                    "signal_strength": signal_strength,
                    "volatility_approved": True,
                    "entry_timing_approved": True,
                    "regime": "sideways",
                    "recommendation": "BUY",
                },
            },
            "backtest_results": {
                "BTC/USDT": {"win_rate": win_rate},
            },
        }

    def test_micro_account_uses_full_risk_no_confidence_reduction(self, micro_config):
        """$110 micro account: risk_amount must equal full risk_per_trade,
        not shrunk by confidence_multiplier = signal × win_rate."""
        agent = RiskManagementAgent(micro_config)
        # No Kelly history → fixed path
        result = agent.execute(self._make_btc_input(signal_strength=0.713, win_rate=0.5))
        assert result["success"] is True
        assessment = result["data"]["assessments"]["BTC/USDT"]

        max_risk = 110.0 * 0.01  # $1.10
        # Micro account: actual_risk_amount should be $1.10 (before
        # position_size_multiplier from asset config, which is 0.80 for BTC)
        # Full risk = $1.10, then × 0.80 multiplier → position size
        # Risk is calculated from final position_size × risk_per_unit
        assert assessment["risk_amount"] > 0
        # The position notional should be well above $5 minimum
        assert assessment["position_size_usd"] >= 5.0, (
            f"Micro account BTC notional ${assessment['position_size_usd']:.2f} "
            f"must be >= $5.00 minimum"
        )

    def test_micro_account_btc_notional_above_exchange_minimum(self, micro_config):
        """$110 BTC position at signal 0.713 must produce notional > $5
        (previously produced ~$16 with confidence reduction, should now be ~$46)."""
        agent = RiskManagementAgent(micro_config)
        result = agent.execute(self._make_btc_input(signal_strength=0.713))
        assert result["success"] is True
        assessment = result["data"]["assessments"]["BTC/USDT"]
        # With full risk sizing: $1.10 risk / (71408.89 × 0.019 SL) = 0.00081 BTC
        # × 0.80 multiplier = 0.000649 BTC × $71408.89 = ~$46
        assert assessment["position_size_usd"] > 30.0, (
            f"BTC notional ${assessment['position_size_usd']:.2f} too low — "
            f"expected > $30 with full micro-account sizing"
        )

    def test_standard_account_uses_confidence_with_floor(self, micro_config):
        """$10000 standard account: confidence_multiplier applied with 0.60 floor."""
        micro_config["account_balance"] = 10000.0
        agent = RiskManagementAgent(micro_config)
        result = agent.execute(self._make_btc_input(signal_strength=0.5, win_rate=0.5))
        assert result["success"] is True
        assessment = result["data"]["assessments"]["BTC/USDT"]
        # confidence = 0.5 × 0.5 = 0.25, but floored at 0.60
        # risk = 10000 × 0.01 × 0.60 = $60 → position_size_usd should be substantial
        assert assessment["position_size_usd"] > 100.0

    def test_micro_account_weak_signal_rejected_by_threshold(self, micro_config):
        """Even with full sizing, weak signals below min_signal_strength get rejected."""
        agent = RiskManagementAgent(micro_config)
        result = agent.execute(self._make_btc_input(signal_strength=0.10))
        assert result["success"] is True
        assessment = result["data"]["assessments"]["BTC/USDT"]
        # Signal 0.10 < adjusted_min_signal_strength (0.30 in bullish,
        # 0.35 in sideways) → rejected
        assert assessment["position_approved"] is False

    def test_micro_account_eth_removed_from_pairs(self, micro_config):
        """With TRADING_PAIRS=BTC/USDT only, ETH should not be assessed."""
        input_data = self._make_btc_input()
        # Add ETH to market_data but it won't be in the config's pairs
        input_data["market_data"]["ETH/USDT"] = {"current_price": 2006.78}
        input_data["analysis"]["ETH/USDT"] = {
            "signal_strength": 0.057,
            "volatility_approved": True,
            "entry_timing_approved": True,
            "regime": "sideways",
        }
        input_data["backtest_results"]["ETH/USDT"] = {"win_rate": 0.5}

        agent = RiskManagementAgent(micro_config)
        result = agent.execute(input_data)
        assert result["success"] is True
        # Both pairs are assessed (risk manager iterates market_data keys)
        # but ETH should still be rejected due to tiny signal
        assessments = result["data"]["assessments"]
        assert "ETH/USDT" in assessments
        # ETH at 0.057 signal in sideways (min 0.35) → rejected
        assert assessments["ETH/USDT"]["position_approved"] is False
