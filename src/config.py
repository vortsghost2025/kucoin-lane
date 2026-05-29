import json
import os
from copy import deepcopy
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _deep_merge(base, override):
    if not isinstance(base, dict):
        return deepcopy(override) if isinstance(override, dict) else override
    merged = deepcopy(base)
    if not isinstance(override, dict):
        return merged
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ASSET_CONFIGS_PATH = _REPO_ROOT / "config" / "asset_profiles.json"

_DEFAULT_ASSET_PROFILES = {
    "risk": {
        "default": {
            "min_signal_strength_adjustment": 0.0,
            "stop_loss_adjustment": 1.0,
            "position_size_multiplier": 1.0,
        },
        "pairs": {
            "SOL/USDT": {
                "min_signal_strength_adjustment": 0.0,
                "stop_loss_adjustment": 1.0,
                "position_size_multiplier": 1.0,
            },
            "BTC/USDT": {
                "min_signal_strength_adjustment": 0.05,
                "stop_loss_adjustment": 0.95,
                "position_size_multiplier": 0.80,
            },
            "ETH/USDT": {
                "min_signal_strength_adjustment": 0.03,
                "stop_loss_adjustment": 0.97,
                "position_size_multiplier": 0.90,
            },
        },
    },
    "market": {
        "default": {
            "rsi_weight": 0.8,
            "momentum_weight": 1.0,
            "volatility_adjustment": 0.1,
            "signal_threshold_adj": 0,
        },
        "pairs": {
            "SOL/USDT": {
                "rsi_weight": 0.8,
                "momentum_weight": 1.0,
                "volatility_adjustment": 0.1,
                "signal_threshold_adj": 0,
            },
            "BTC/USDT": {
                "rsi_weight": 0.6,
                "momentum_weight": 1.2,
                "volatility_adjustment": 0.05,
                "signal_threshold_adj": 5,
            },
            "ETH/USDT": {
                "rsi_weight": 0.7,
                "momentum_weight": 1.1,
                "volatility_adjustment": 0.07,
                "signal_threshold_adj": 3,
            },
        },
    },
    "backtest": {
        "default": {
            "win_rate_multiplier": 1.0,
            "max_drawdown_adjustment": 1.0,
        },
        "pairs": {
            "SOL/USDT": {
                "win_rate_multiplier": 1.0,
                "max_drawdown_adjustment": 1.0,
            },
            "BTC/USDT": {
                "win_rate_multiplier": 0.87,
                "max_drawdown_adjustment": 1.15,
            },
            "ETH/USDT": {
                "win_rate_multiplier": 0.90,
                "max_drawdown_adjustment": 1.10,
            },
        },
    },
}


def _read_json_file(path_value: str):
    try:
        with open(path_value, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_asset_profiles():
    profiles = deepcopy(_DEFAULT_ASSET_PROFILES)

    asset_path = os.getenv("ASSET_CONFIGS_PATH", str(_DEFAULT_ASSET_CONFIGS_PATH))
    file_profiles = _read_json_file(asset_path)
    if isinstance(file_profiles, dict):
        profiles = _deep_merge(profiles, file_profiles)

    inline_json = os.getenv("ASSET_CONFIGS_JSON", "")
    if inline_json:
        try:
            inline_profiles = json.loads(inline_json)
            if isinstance(inline_profiles, dict):
                profiles = _deep_merge(profiles, inline_profiles)
        except json.JSONDecodeError:
            pass

    return profiles


ASSET_PROFILES = _load_asset_profiles()


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
    "asset_config_default": deepcopy(ASSET_PROFILES["risk"]["default"]),
    "asset_configs": deepcopy(ASSET_PROFILES["risk"]["pairs"]),
    "max_position_size_usd": float(os.getenv("MAX_POSITION_SIZE_USD", "10.0")),
}

MARKET_CONFIG = {
    "rsi_period": int(os.getenv("RSI_PERIOD", "14")),
    "macd_fast": int(os.getenv("MACD_FAST", "12")),
    "macd_slow": int(os.getenv("MACD_SLOW", "26")),
    "macd_signal": int(os.getenv("MACD_SIGNAL", "9")),
    "downtrend_threshold": float(os.getenv("DOWNTREND_THRESHOLD", "-5")),
    "asset_config_default": deepcopy(ASSET_PROFILES["market"]["default"]),
    "asset_configs": deepcopy(ASSET_PROFILES["market"]["pairs"]),
}

BACKTEST_CONFIG = {
    "min_win_rate": float(os.getenv("BACKTEST_MIN_WIN_RATE", "0.45")),
    "max_drawdown": float(os.getenv("BACKTEST_MAX_DRAWDOWN", "0.15")),
    "asset_factor_default": deepcopy(ASSET_PROFILES["backtest"]["default"]),
    "asset_performance_factors": deepcopy(ASSET_PROFILES["backtest"]["pairs"]),
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

KUCOIN_API_KEY = API_CONFIG["api_key"]
KUCOIN_API_SECRET = API_CONFIG["api_secret"]
KUCOIN_API_PASSPHRASE = API_CONFIG["api_passphrase"]

POSITION_SIZE_USD = float(os.getenv("POSITION_SIZE_USD", "5.0"))
MONITOR_INTERVAL_MIN = int(os.getenv("MONITOR_INTERVAL_MIN", "5"))

DRY_RUN = TRADING_CONFIG["paper_trading"]
LIVE_TRADING = os.getenv("LIVE_TRADING", "false").lower() == "true"


MAX_POSITION_SIZE_USD_GLOBAL = float(os.getenv("MAX_POSITION_SIZE_USD", "10.0"))
MAX_TRADE_LOSS_USD = float(os.getenv("MAX_TRADE_LOSS_USD", "5.0"))
MAX_DAILY_LOSS_USD = float(os.getenv("MAX_DAILY_LOSS_USD", "10.0"))
MIN_BALANCE_USD = float(os.getenv("MIN_BALANCE_USD", "10.0"))
