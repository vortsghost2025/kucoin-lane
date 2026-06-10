import os
import importlib
import pytest
from src import config as cfg


class TestConfigEnvVarCoercion:
    def test_bool_coercion_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("PAPER_TRADING", "TRUE")
        importlib.reload(cfg)
        assert cfg.TRADING_CONFIG["paper_trading"] is True
        monkeypatch.setenv("PAPER_TRADING", "False")
        importlib.reload(cfg)
        assert cfg.TRADING_CONFIG["paper_trading"] is False

    def test_bool_coercion_unexpected_value(self, monkeypatch):
        monkeypatch.setenv("PAPER_TRADING", "maybe")
        importlib.reload(cfg)
        assert cfg.TRADING_CONFIG["paper_trading"] is False

    def test_bool_coercion_empty_string(self, monkeypatch):
        monkeypatch.setenv("PAPER_TRADING", "")
        importlib.reload(cfg)
        assert cfg.TRADING_CONFIG["paper_trading"] is False

    def test_float_coercion_from_env(self, monkeypatch):
        monkeypatch.setenv("RISK_PER_TRADE", "0.02")
        importlib.reload(cfg)
        assert cfg.RISK_CONFIG["risk_per_trade"] == 0.02

    def test_float_coercion_integer_string(self, monkeypatch):
        monkeypatch.setenv("ACCOUNT_BALANCE", "100")
        importlib.reload(cfg)
        assert cfg.TRADING_CONFIG["account_balance"] == 100.0

    def test_int_coercion_from_env(self, monkeypatch):
        monkeypatch.setenv("RSI_PERIOD", "21")
        importlib.reload(cfg)
        assert cfg.MARKET_CONFIG["rsi_period"] == 21

    def test_int_coercion_float_string_raises(self, monkeypatch):
        monkeypatch.setenv("RSI_PERIOD", "14.5")
        with pytest.raises(ValueError):
            importlib.reload(cfg)


class TestConfigBoundaryValues:
    def test_zero_account_balance(self, monkeypatch):
        monkeypatch.setenv("ACCOUNT_BALANCE", "0")
        importlib.reload(cfg)
        assert cfg.TRADING_CONFIG["account_balance"] == 0.0

    def test_negative_account_balance(self, monkeypatch):
        monkeypatch.setenv("ACCOUNT_BALANCE", "-10")
        importlib.reload(cfg)
        assert cfg.TRADING_CONFIG["account_balance"] == -10.0

    def test_zero_risk_per_trade(self, monkeypatch):
        monkeypatch.setenv("RISK_PER_TRADE", "0")
        importlib.reload(cfg)
        assert cfg.RISK_CONFIG["risk_per_trade"] == 0.0

    def test_very_large_position_size(self, monkeypatch):
        monkeypatch.setenv("POSITION_SIZE_USD", "999999")
        importlib.reload(cfg)
        assert cfg.POSITION_SIZE_USD == 999999.0

    def test_trading_pairs_single(self, monkeypatch):
        monkeypatch.setenv("TRADING_PAIRS", "BTC/USDT")
        importlib.reload(cfg)
        assert cfg.TRADING_CONFIG["trading_pairs"] == ["BTC/USDT"]

    def test_trading_pairs_trailing_comma(self, monkeypatch):
        monkeypatch.setenv("TRADING_PAIRS", "SOL/USDT,BTC/USDT,")
        importlib.reload(cfg)
        assert cfg.TRADING_CONFIG["trading_pairs"] == ["SOL/USDT", "BTC/USDT", ""]


class TestConfigMissingVars:
    def test_api_config_defaults_when_unset(self, monkeypatch):
        import src.config as local_cfg
        if local_cfg.KUCOIN_API_KEY:
            pytest.skip("KuCoin keys present in .env - test requires empty env")
        monkeypatch.delenv("KUCOIN_API_KEY", raising=False)
        monkeypatch.delenv("KUCOIN_API_SECRET", raising=False)
        monkeypatch.delenv("KUCOIN_API_PASSPHRASE", raising=False)
        monkeypatch.setattr("src.config.load_dotenv", lambda x: None)
        importlib.reload(cfg)
        assert cfg.API_CONFIG["api_key"] == ""
        assert cfg.API_CONFIG["api_secret"] == ""
        assert cfg.API_CONFIG["api_passphrase"] == ""

    def test_telegram_config_defaults_when_unset(self, monkeypatch):
        for var in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
            monkeypatch.delenv(var, raising=False)
        importlib.reload(cfg)
        assert cfg.TELEGRAM_CONFIG["bot_token"] == ""
        assert cfg.TELEGRAM_CONFIG["chat_id"] == ""

    def test_regime_guard_mode_default(self, monkeypatch):
        monkeypatch.delenv("REGIME_GUARD_MODE", raising=False)
        importlib.reload(cfg)
        assert cfg.REGIME_GUARD_MODE == "v1_soft_halt"


class TestConfigAliases:
    def test_dry_run_equals_paper_trading(self, monkeypatch):
        monkeypatch.setenv("PAPER_TRADING", "false")
        importlib.reload(cfg)
        assert cfg.DRY_RUN is False
        assert cfg.DRY_RUN == cfg.TRADING_CONFIG["paper_trading"]

    def test_live_trading_independent_of_paper(self, monkeypatch):
        monkeypatch.setenv("PAPER_TRADING", "true")
        monkeypatch.setenv("LIVE_TRADING", "true")
        importlib.reload(cfg)
        assert cfg.DRY_RUN is True
        assert cfg.LIVE_TRADING is True

    def test_kucoin_aliases_match_api_config(self, monkeypatch):
        monkeypatch.setenv("KUCOIN_API_KEY", "testkey")
        importlib.reload(cfg)
        assert cfg.KUCOIN_API_KEY == "testkey"
        assert cfg.KUCOIN_API_KEY == cfg.API_CONFIG["api_key"]

    def test_max_position_size_usd_global(self, monkeypatch):
        monkeypatch.setenv("MAX_POSITION_SIZE_USD", "25")
        importlib.reload(cfg)
        assert cfg.MAX_POSITION_SIZE_USD_GLOBAL == 25.0

    def test_monitor_interval_int(self, monkeypatch):
        monkeypatch.setenv("MONITOR_INTERVAL_MIN", "15")
        importlib.reload(cfg)
        assert cfg.MONITOR_INTERVAL_MIN == 15
        assert isinstance(cfg.MONITOR_INTERVAL_MIN, int)
