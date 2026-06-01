"""Centralized timeframe constants and helpers.

All timeframe-related constants and logic that were previously duplicated
across multiple modules are consolidated here.
"""

import os
from typing import Dict, Optional, Set

# ── Canonical interval sets ──────────────────────────────────────────────

# All intervals the KuCoin API supports
SUPPORTED_INTERVALS: Set[str] = {
    "1min", "3min", "5min", "15min", "30min",
    "1hour", "2hour", "4hour", "6hour", "8hour", "12hour",
    "1day", "1week",
}

# ── Timeframe-to-value mappings ──────────────────────────────────────────

# Number of candle bars in 24 hours per timeframe
BARS_PER_DAY: Dict[str, int] = {
    "1min": 1440,
    "5min": 288,
    "15min": 96,
    "30min": 48,
    "1hour": 24,
    "6hour": 4,
    "1day": 1,
}

# Cache TTL per interval (seconds) — from kucoin_klines_fetcher.py
INTERVAL_CACHE_TIMEOUTS: Dict[str, int] = {
    "1min": 60,
    "3min": 180,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1hour": 3600,
    "2hour": 7200,
    "4hour": 14400,
    "6hour": 21600,
    "8hour": 28800,
    "12hour": 43200,
    "1day": 86400,
    "1week": 604800,
}

# ATR high-volatility threshold per timeframe — from regime_detector.py
ATR_THRESHOLD_BY_TIMEFRAME: Dict[str, float] = {
    "1min": 0.01,
    "5min": 0.02,
    "15min": 0.025,
    "30min": 0.03,
    "1hour": 0.04,
    "6hour": 0.10,
    "1day": 0.15,
}

# ── Default ──────────────────────────────────────────────────────────────

DEFAULT_TIMEFRAME = "1hour"

# ── Helper functions ─────────────────────────────────────────────────────


def resolve_timeframe(config: dict) -> str:
    """Return timeframe from config dict, falling back to CANDLE_INTERVAL
    env var, then default.

    Unifies the inconsistent fallback logic across the codebase:
    - risk_manager, backtester, market_analyzer: cfg.get("timeframe", None) → could be None
    - orchestrator: config.get("timeframe") or os.getenv("CANDLE_INTERVAL", "1hour")
    - execution_engine: orch_config.setdefault("timeframe", os.getenv("CANDLE_INTERVAL", "1hour"))

    Now all use the same chain: config → env var → DEFAULT_TIMEFRAME
    """
    return config.get("timeframe") or os.getenv("CANDLE_INTERVAL", DEFAULT_TIMEFRAME)


def apply_timeframe_overrides(base: dict, per_asset: dict, timeframe: str) -> dict:
    """Merge timeframe-specific overrides from per_asset['timeframe_overrides']
    into base dict.

    Replaces the 7 identical copy-pasted blocks across risk_manager (1x),
    backtester (4x), and market_analyzer (2x).

    Args:
        base: The base config/factor dict to merge into (e.g., asset_config, asset_factor)
        per_asset: The per-asset dict that may contain a 'timeframe_overrides' sub-dict
        timeframe: The active timeframe string (e.g., "1hour", "6hour")

    Returns:
        New dict with timeframe overrides deep-merged into base, or base unchanged
        if no matching override exists.

    Example:
        asset_config = {"signal_threshold": 55, "position_multiplier": 1.0}
        per_asset = {"timeframe_overrides": {"6hour": {"signal_threshold": 60}}}
        result = apply_timeframe_overrides(asset_config, per_asset, "6hour")
        # result = {"signal_threshold": 60, "position_multiplier": 1.0}
    """
    if not timeframe:
        return base
    tf_overrides = per_asset.get("timeframe_overrides", {})
    if (
        isinstance(tf_overrides, dict)
        and timeframe in tf_overrides
        and isinstance(tf_overrides[timeframe], dict)
    ):
        return {**base, **tf_overrides[timeframe]}
    return base


def get_bars_per_day(timeframe: str) -> int:
    """Return number of bars per 24h for the given timeframe.

    Falls back to computing from the interval string for non-standard intervals.
    """
    if timeframe in BARS_PER_DAY:
        return BARS_PER_DAY[timeframe]
    # Fallback: try to parse "Xhour", "Xmin" etc.
    try:
        if timeframe.endswith("hour"):
            hours = int(timeframe.replace("hour", ""))
            return 24 // hours
        elif timeframe.endswith("min"):
            minutes = int(timeframe.replace("min", ""))
            return 1440 // minutes
        elif timeframe.endswith("day"):
            return 1
    except (ValueError, ZeroDivisionError):
        pass
    return 24  # sensible default: assume 1hour-like


def get_atr_threshold(timeframe: str) -> float:
    """Return ATR high-volatility threshold for the given timeframe.

    Falls back to linear interpolation for non-standard intervals.
    """
    if timeframe in ATR_THRESHOLD_BY_TIMEFRAME:
        return ATR_THRESHOLD_BY_TIMEFRAME[timeframe]
    # Default: use 1hour threshold (0.04) as middle-ground
    return ATR_THRESHOLD_BY_TIMEFRAME.get(DEFAULT_TIMEFRAME, 0.04)


def get_cache_timeout(interval: str) -> int:
    """Return cache TTL in seconds for the given interval.

    Falls back to proportional scaling based on interval duration.
    """
    if interval in INTERVAL_CACHE_TIMEOUTS:
        return INTERVAL_CACHE_TIMEOUTS[interval]
    # Default: 1 hour
    return 3600
