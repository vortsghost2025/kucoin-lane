import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


TRADING_CONFIG = {
    "account_balance": float(os.getenv("ACCOUNT_BALANCE", "80")),
    "paper_trading": os.getenv("PAPER_TRADING", "true").lower() == "true",
    "trading_pairs": os.getenv("TRADING_PAIRS", "SOL/USDT,BTC/USDT,ETH/USDT").split(
        ","
    ),
}

RISK_CONFIG = {
    "risk_per_trade": float(os.getenv("RISK_PER_TRADE", "0.005")),
    "min_risk_reward_ratio": float(os.getenv("MIN_RISK_REWARD_RATIO", "1.5")),
    "max_daily_loss": float(os.getenv("MAX_DAILY_LOSS", "0.05")),
    "account_balance": float(os.getenv("ACCOUNT_BALANCE", "80")),
    "min_signal_strength": float(os.getenv("MIN_SIGNAL_STRENGTH", "0.25")),
    "min_win_rate": float(os.getenv("MIN_WIN_RATE", "0.45")),
    "min_notional_usd": float(os.getenv("MIN_NOTIONAL_USD", "1.0")),
    "default_stop_loss_pct": float(os.getenv("DEFAULT_STOP_LOSS_PCT", "0.02")),
    "enforce_min_position_size_only": os.getenv(
        "ENFORCE_MIN_POSITION_SIZE_ONLY", "false"
    ).lower()
    == "true",
    "min_position_size_units": float(os.getenv("MIN_POSITION_SIZE_UNITS", "0.01")),
    "min_position_size_by_pair": {
        "SOL/USDT": float(os.getenv("MIN_SIZE_SOL", "0.01")),
        "BTC/USDT": float(os.getenv("MIN_SIZE_BTC", "0.0001")),
        "ETH/USDT": float(os.getenv("MIN_SIZE_ETH", "0.001")),
    },
    "max_position_size_usd": float(os.getenv("MAX_POSITION_SIZE_USD", "10.0")),
}

MARKET_CONFIG = {
    "rsi_period": int(os.getenv("RSI_PERIOD", "14")),
    "macd_fast": int(os.getenv("MACD_FAST", "12")),
    "macd_slow": int(os.getenv("MACD_SLOW", "26")),
    "macd_signal": int(os.getenv("MACD_SIGNAL", "9")),
    "downtrend_threshold": float(os.getenv("DOWNTREND_THRESHOLD", "-5")),
}

BACKTEST_CONFIG = {
    "min_win_rate": float(os.getenv("BACKTEST_MIN_WIN_RATE", "0.45")),
    "max_drawdown": float(os.getenv("BACKTEST_MAX_DRAWDOWN", "0.15")),
}

DATA_CONFIG = {
    "cache_timeout": int(os.getenv("CACHE_TIMEOUT", "300")),
    "api_timeout": int(os.getenv("API_TIMEOUT", "10")),
}

API_CONFIG = {
    "api_key": os.getenv("KUCOIN_API_KEY", ""),
    "api_secret": os.getenv("KUCOIN_API_SECRET", ""),
    "api_passphrase": os.getenv("KUCOIN_API_PASSPHRASE", ""),
}

EXECUTION_CONFIG = {
    "paper_trading": os.getenv("PAPER_TRADING", "true").lower() == "true",
    "max_open_positions": int(os.getenv("MAX_OPEN_POSITIONS", "1")),
}

ENTRY_TIMING_CONFIG = {
    "enabled": os.getenv("ENTRY_TIMING_ENABLED", "true").lower() == "true",
    "reversal_threshold_pct": float(os.getenv("REVERSAL_THRESHOLD_PCT", "0.001")),
}

MONITOR_CONFIG = {
    "logs_dir": os.getenv("LOGS_DIR", "./logs"),
    "enable_alerts": os.getenv("ENABLE_ALERTS", "true").lower() == "true",
    "alert_level": os.getenv("ALERT_LEVEL", "WARNING"),
}

REGIME_GUARD_MODE = os.getenv("REGIME_GUARD_MODE", "v1_soft_halt")

TELEGRAM_CONFIG = {
    "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
}
