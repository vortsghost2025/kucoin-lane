import os
import pytest
import importlib
from src import config as cfg


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    env_vars = [
        "RISK_PER_TRADE", "MIN_RISK_REWARD_RATIO", "MAX_DAILY_LOSS",
        "DEFAULT_STOP_LOSS_PCT", "MIN_NOTIONAL_USD", "MAX_POSITION_SIZE_USD",
        "MAX_OPEN_POSITIONS", "PAPER_TRADING", "ACCOUNT_BALANCE",
        "RSI_PERIOD", "MACD_FAST", "MACD_SLOW", "MACD_SIGNAL",
        "DOWNTREND_THRESHOLD", "MIN_SIGNAL_STRENGTH", "MIN_WIN_RATE",
        "KUCOIN_API_KEY", "KUCOIN_API_SECRET", "KUCOIN_API_PASSPHRASE",
        "TRADING_PAIRS", "STRATEGY", "STRATEGY_PARAMS_JSON",
        "CACHE_TIMEOUT", "API_TIMEOUT", "BACKTEST_MIN_WIN_RATE",
        "BACKTEST_MAX_DRAWDOWN", "TRAILING_ACTIVATION_PCT",
        "TRAILING_PCT", "TRAILING_STEP_PCT", "BREAKEVEN_ACTIVATION_PCT",
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
        "REGIME_GUARD_MODE", "ENTRY_TIMING_ENABLED",
        "REVERSAL_THRESHOLD_PCT", "CANDLE_INTERVAL",
        "MIN_SIZE_BTC", "MIN_SIZE_ETH", "MIN_SIZE_AVAX",
        "MIN_SIZE_DOGE", "MIN_SIZE_LINK",
        "POSITION_SIZE_USD", "MONITOR_INTERVAL_MIN",
        "ENFORCE_MIN_POSITION_SIZE_ONLY",
        "MIN_POSITION_SIZE_UNITS",
        "ASSET_CONFIGS_PATH", "MODE", "SPOT_LONG_ONLY",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    importlib.reload(cfg)
    yield
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    importlib.reload(cfg)


class TestConfigModule:
    def test_trading_config_defaults(self):
        assert "trading_pairs" in cfg.TRADING_CONFIG
        assert cfg.TRADING_CONFIG["paper_trading"] is True
        assert cfg.TRADING_CONFIG["account_balance"] == 110.0

    def test_risk_config_defaults(self):
        assert cfg.RISK_CONFIG["risk_per_trade"] == 0.01
        assert cfg.RISK_CONFIG["min_risk_reward_ratio"] == 2.0
        assert cfg.RISK_CONFIG["max_daily_loss"] == 0.05
        assert cfg.RISK_CONFIG["default_stop_loss_pct"] == 0.02
        assert cfg.RISK_CONFIG["min_notional_usd"] == 5.0
        assert cfg.RISK_CONFIG["max_position_size_usd"] == 55.0

    def test_market_config_defaults(self):
        assert cfg.MARKET_CONFIG["rsi_period"] == 14
        assert cfg.MARKET_CONFIG["macd_fast"] == 12
        assert cfg.MARKET_CONFIG["macd_slow"] == 26
        assert cfg.MARKET_CONFIG["downtrend_threshold"] == -5

    def test_api_config_empty_by_default(self):
        assert cfg.API_CONFIG["api_key"] == ""
        assert cfg.API_CONFIG["api_secret"] == ""
        assert cfg.API_CONFIG["api_passphrase"] == ""

    def test_execution_config_paper_trading_default(self):
        assert cfg.EXECUTION_CONFIG["paper_trading"] is True
        assert cfg.EXECUTION_CONFIG["max_open_positions"] == 2

    def test_execution_config_trailing_stop_defaults(self):
        ts = cfg.EXECUTION_CONFIG["trailing_stop_config"]
        assert ts["activation_pct"] == 2.0
        assert ts["trail_pct"] == 1.5
        assert ts["step_pct"] == 0.5

    def test_execution_config_custom_stoploss_defaults(self):
        cs = cfg.EXECUTION_CONFIG["custom_stoploss_config"]
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

        importlib.reload(cfg)

        assert cfg.TRADING_CONFIG["paper_trading"] is False
        assert cfg.TRADING_CONFIG["account_balance"] == 200.0
        assert cfg.MARKET_CONFIG["rsi_period"] == 7

    def test_telegram_config_defaults(self):
        assert cfg.TELEGRAM_CONFIG["bot_token"] == ""
        assert cfg.TELEGRAM_CONFIG["chat_id"] == ""

    def test_regime_guard_mode_default(self):
        assert cfg.REGIME_GUARD_MODE == "v1_soft_halt"

    def test_entry_timing_config_defaults(self):
        assert cfg.ENTRY_TIMING_CONFIG["enabled"] is True
        assert cfg.ENTRY_TIMING_CONFIG["reversal_threshold_pct"] == 0.001
