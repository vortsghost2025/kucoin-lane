import os
import pytest


class TestConfigModule:
    def test_trading_config_defaults(self):
        from src.config import TRADING_CONFIG
        assert "trading_pairs" in TRADING_CONFIG
        assert TRADING_CONFIG["paper_trading"] is True
        assert TRADING_CONFIG["account_balance"] == 110.0

    def test_risk_config_defaults(self):
        from src.config import RISK_CONFIG
        assert RISK_CONFIG["risk_per_trade"] == 0.01
        assert RISK_CONFIG["min_risk_reward_ratio"] == 2.0
        assert RISK_CONFIG["max_daily_loss"] == 0.05
        assert RISK_CONFIG["default_stop_loss_pct"] == 0.02
        assert RISK_CONFIG["min_notional_usd"] == 5.0
        assert RISK_CONFIG["max_position_size_usd"] == 55.0

    def test_market_config_defaults(self):
        from src.config import MARKET_CONFIG
        assert MARKET_CONFIG["rsi_period"] == 14
        assert MARKET_CONFIG["macd_fast"] == 12
        assert MARKET_CONFIG["macd_slow"] == 26
        assert MARKET_CONFIG["downtrend_threshold"] == -5

    def test_api_config_empty_by_default(self):
        from src.config import API_CONFIG
        assert API_CONFIG["api_key"] == ""
        assert API_CONFIG["api_secret"] == ""
        assert API_CONFIG["api_passphrase"] == ""

    def test_execution_config_paper_trading_default(self):
        from src.config import EXECUTION_CONFIG
        assert EXECUTION_CONFIG["paper_trading"] is True
        assert EXECUTION_CONFIG["max_open_positions"] == 2

    def test_execution_config_trailing_stop_defaults(self):
        from src.config import EXECUTION_CONFIG
        ts = EXECUTION_CONFIG["trailing_stop_config"]
        assert ts["activation_pct"] == 2.0
        assert ts["trail_pct"] == 1.5
        assert ts["step_pct"] == 0.5

    def test_execution_config_custom_stoploss_defaults(self):
        from src.config import EXECUTION_CONFIG
        cs = EXECUTION_CONFIG["custom_stoploss_config"]
        assert cs["breakeven_activation_pct"] == 1.0

    def test_module_level_aliases(self):
        from src.config import (
            KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE,
            POSITION_SIZE_USD, MONITOR_INTERVAL_MIN, DRY_RUN, LIVE_TRADING,
        )
        assert KUCOIN_API_KEY == ""
        assert KUCOIN_API_SECRET == ""
        assert KUCOIN_API_PASSPHRASE == ""
        assert POSITION_SIZE_USD == 55.0
        assert MONITOR_INTERVAL_MIN == 5
        assert DRY_RUN is True
        assert LIVE_TRADING is False

    def test_env_var_overrides(self, monkeypatch):
        monkeypatch.setenv("PAPER_TRADING", "false")
        monkeypatch.setenv("ACCOUNT_BALANCE", "200")
        monkeypatch.setenv("RSI_PERIOD", "7")

        import importlib
        from src import config as cfg
        importlib.reload(cfg)

        assert cfg.TRADING_CONFIG["paper_trading"] is False
        assert cfg.TRADING_CONFIG["account_balance"] == 200.0
        assert cfg.MARKET_CONFIG["rsi_period"] == 7

    def test_telegram_config_defaults(self):
        from src.config import TELEGRAM_CONFIG
        assert TELEGRAM_CONFIG["bot_token"] == ""
        assert TELEGRAM_CONFIG["chat_id"] == ""

    def test_regime_guard_mode_default(self):
        from src.config import REGIME_GUARD_MODE
        assert REGIME_GUARD_MODE == "v1_soft_halt"

    def test_entry_timing_config_defaults(self):
        from src.config import ENTRY_TIMING_CONFIG
        assert ENTRY_TIMING_CONFIG["enabled"] is True
        assert ENTRY_TIMING_CONFIG["reversal_threshold_pct"] == 0.001
