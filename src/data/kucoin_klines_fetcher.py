"""
KuCoin Klines/OHLCV Data Fetcher
=================================

Fetches kline (candlestick) data from KuCoin and converts it to
properly-formatted OHLCV pandas DataFrames for use by RegimeDetector
and WhaleWatch intelligence modules.

Key detail: KuCoin klines API returns fields in NON-STANDARD order:
  [timestamp, open, close, high, low, volume_base, volume_quote]
This module reorders to standard OHLCV: [open, high, low, close, volume].

KuCoin klines endpoint is PUBLIC — no API key required.
Rate limit: ~9 requests/second per IP (conservative: 1 req/sec).
Max 1500 candles per request.
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_MIN_INTERVAL_SECONDS = 1.0
_lock = threading.Lock()
_last_call_ts = 0.0

SUPPORTED_INTERVALS = {
    "1min",
    "3min",
    "5min",
    "15min",
    "30min",
    "1hour",
    "2hour",
    "4hour",
    "6hour",
    "8hour",
    "12hour",
    "1day",
    "1week",
}

INTERVAL_CACHE_TIMEOUTS = {
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

DEFAULT_CANDLE_COUNT = 100


class KuCoinKlinesFetcher:
    """Fetches and caches KuCoin kline data, converting to OHLCV DataFrames."""

    def __init__(
        self,
        default_interval: str = "5min",
        default_candle_count: int = DEFAULT_CANDLE_COUNT,
        cache_enabled: bool = True,
    ):
        self.default_interval = default_interval
        self.default_candle_count = default_candle_count
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _rate_limited_get_klines(
        self,
        adapter,
        symbol: str,
        interval: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
    ) -> List[List]:
        """Rate-limited kline fetch via the exchange adapter."""
        global _last_call_ts
        with _lock:
            now = time.time()
            wait = _MIN_INTERVAL_SECONDS - (now - _last_call_ts)
            if wait > 0:
                time.sleep(wait)
            _last_call_ts = time.time()
        return adapter.get_klines(symbol, interval, start, end)

    def _cache_key(self, symbol: str, interval: str) -> str:
        return f"{symbol}_{interval}"

    def _is_cache_valid(self, cache_key: str, interval: str) -> bool:
        if cache_key not in self._cache:
            return False
        cached_time = self._cache[cache_key].get("timestamp")
        if not cached_time:
            return False
        timeout = INTERVAL_CACHE_TIMEOUTS.get(interval, 300)
        age = (datetime.now(timezone.utc) - cached_time).total_seconds()
        return age < timeout

    @staticmethod
    def raw_klines_to_dataframe(raw_klines: List[List]) -> pd.DataFrame:
        """Convert raw KuCoin kline data to a properly-formatted OHLCV DataFrame.

        KuCoin returns: [timestamp, open, close, high, low, volume_base, volume_quote]
        We reorder to: open, high, low, close, volume (standard OHLCV)

        Args:
            raw_klines: List of lists from KuCoin API

        Returns:
            pd.DataFrame with columns: timestamp, open, high, low, close, volume
            Sorted by timestamp ascending, oldest first.
        """
        if not raw_klines:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        rows = []
        for candle in raw_klines:
            try:
                ts = int(candle[0])
                open_price = float(candle[1])
                close_price = float(candle[2])
                high = float(candle[3])
                low = float(candle[4])
                volume = float(candle[5])
                rows.append({
                    "timestamp": ts,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close_price,
                    "volume": volume,
                })
            except (IndexError, ValueError, TypeError) as e:
                logger.warning(f"Skipping malformed kline candle: {e}")
                continue

        if not rows:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def fetch_klines(
        self,
        adapter,
        symbol: str,
        interval: Optional[str] = None,
        candle_count: Optional[int] = None,
    ) -> Optional[pd.DataFrame]:
        """Fetch kline data and return an OHLCV DataFrame.

        Args:
            adapter: KuCoinAdapter instance (or any ExchangeAdapter with get_klines)
            symbol: Trading pair in BASE/QUOTE format (e.g., "SOL/USDT")
            interval: Candle interval (default: self.default_interval)
            candle_count: Number of candles to fetch (default: self.default_candle_count)

        Returns:
            pd.DataFrame with columns: timestamp, open, high, low, close, volume
            Returns None on failure.
        """
        interval = interval or self.default_interval
        candle_count = candle_count or self.default_candle_count

        if interval not in SUPPORTED_INTERVALS:
            logger.error(f"Unsupported kline interval: {interval}. Supported: {SUPPORTED_INTERVALS}")
            return None

        cache_key = self._cache_key(symbol, interval)

        if self.cache_enabled and self._is_cache_valid(cache_key, interval):
            logger.debug(f"Using cached klines for {symbol} ({interval})")
            return self._cache[cache_key]["df"].copy()

        interval_seconds = self._interval_to_seconds(interval)
        end_ts = int(time.time())
        start_ts = end_ts - (candle_count * interval_seconds)

        try:
            raw_klines = self._rate_limited_get_klines(
                adapter,
                symbol,
                interval,
                start=start_ts,
                end=end_ts,
            )
        except Exception as e:
            logger.error(f"Klines fetch failed for {symbol} ({interval}): {e}")
            return None

        if not raw_klines:
            logger.warning(f"No kline data returned for {symbol} ({interval})")
            return None

        df = self.raw_klines_to_dataframe(raw_klines)

        if df.empty:
            logger.warning(f"Empty DataFrame after kline conversion for {symbol}")
            return None

        min_required = 15
        if len(df) < min_required:
            logger.warning(
                f"Insufficient kline data for {symbol}: {len(df)} rows "
                f"(need {min_required}+ for regime detection)"
            )

        if self.cache_enabled:
            self._cache[cache_key] = {
                "df": df.copy(),
                "timestamp": datetime.now(timezone.utc),
            }

        logger.info(
            f"Fetched {len(df)} klines for {symbol} ({interval}): "
            f"{df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}"
        )
        return df

    def fetch_klines_multi(
        self,
        adapter,
        symbols: List[str],
        interval: Optional[str] = None,
        candle_count: Optional[int] = None,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch klines for multiple symbols.

        Returns:
            Dict mapping symbol -> DataFrame (symbols with failures are omitted)
        """
        results = {}
        for symbol in symbols:
            df = self.fetch_klines(adapter, symbol, interval, candle_count)
            if df is not None and not df.empty:
                results[symbol] = df
        return results

    @staticmethod
    def _interval_to_seconds(interval: str) -> int:
        """Convert KuCoin interval string to seconds."""
        mapping = {
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
        return mapping.get(interval, 300)

    def clear_cache(self) -> None:
        self._cache.clear()
        logger.info("Klines cache cleared")

    def get_cache_status(self) -> Dict[str, Any]:
        return {
            "total_entries": len(self._cache),
            "entries": {
                k: {
                    "rows": len(v["df"]),
                    "age_seconds": (
                        datetime.now(timezone.utc) - v["timestamp"]
                    ).total_seconds(),
                }
                for k, v in self._cache.items()
            },
        }
