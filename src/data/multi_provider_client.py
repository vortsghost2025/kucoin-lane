"""Multi-provider market data client (Binance -> Kraken -> CoinGecko + DEX intelligence)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Iterable, Optional

import requests

from .coingecko_client import fetch_simple_price as coingecko_fetch_simple_price

logger = logging.getLogger(__name__)

BINANCE_BASE_URL = "https://api.binance.com"
KRAKEN_BASE_URL = "https://api.kraken.com"
DEXSCREENER_BASE_URL = "https://api.dexscreener.com"
GECKOTERMINAL_BASE_URL = "https://api.geckoterminal.com"

MIN_INTERVAL_SECONDS = 1.0
MAX_RETRIES = 3
TIMEOUT_SECONDS = 10

_lock = threading.Lock()
_last_call_ts = 0.0


COINGECKO_ID_TO_BASE = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "usd-coin": "USDC",
    "tether": "USDT",
    "raydium": "RAY",
    "orca": "ORCA",
}

BINANCE_SYMBOLS = {
    "bitcoin": "BTCUSDT",
    "ethereum": "ETHUSDT",
    "solana": "SOLUSDT",
    "usd-coin": "USDCUSDT",
    "tether": "USDTUSDT",
    "raydium": "RAYUSDT",
    "orca": "ORCAUSDT",
}

KRAKEN_SYMBOLS = {
    "bitcoin": "XBTUSD",
    "ethereum": "ETHUSD",
    "solana": "SOLUSD",
    "usd-coin": "USDCUSD",
    "tether": "USDTUSD",
}

DEXSCRENER_CHAIN_MAP = {
    "solana": "solana",
    "ethereum": "ethereum",
    "base": "base",
    "arbitrum": "arbitrum",
    "bsc": "bsc",
}

DEX_SIGNAL_THRESHOLDS = {
    "min_liquidity_usd": 50000.0,
    "min_volume_24h_usd": 10000.0,
    "min_composite_score": 0.4,
}


def _rate_limited_get(
    url: str, params: Optional[Dict[str, Any]] = None
) -> requests.Response:
    global _last_call_ts

    with _lock:
        now = time.time()
        wait = MIN_INTERVAL_SECONDS - (now - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
        response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
        _last_call_ts = time.time()

    return response


def _safe_get(url: str, params: Optional[Dict[str, Any]] = None) -> requests.Response:
    last_exc: Optional[Exception] = None

    for attempt in range(MAX_RETRIES):
        try:
            response = _rate_limited_get(url, params=params)
            if response.status_code in {418, 429}:
                sleep_time = (attempt + 1) * 2
                time.sleep(sleep_time)
                continue
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < (MAX_RETRIES - 1):
                time.sleep((attempt + 1) * 2)
                continue
            raise

    if last_exc:
        raise last_exc
    raise RuntimeError("Market data request failed without response")


def _to_coin_gecko_shape(
    coingecko_id: str,
    price: float,
    volume_24h: float = 0.0,
    price_change_24h: float = 0.0,
) -> Dict[str, Any]:
    return {
        coingecko_id: {
            "usd": price,
            "usd_24h_vol": volume_24h,
            "usd_24h_change": price_change_24h,
            "market_cap": {"usd": 0},
        }
    }


def _fetch_binance(coingecko_id: str) -> Optional[Dict[str, Any]]:
    symbol = BINANCE_SYMBOLS.get(coingecko_id)
    if not symbol:
        return None

    url = f"{BINANCE_BASE_URL}/api/v3/ticker/24hr"
    params = {"symbol": symbol}
    response = _safe_get(url, params=params)
    data = response.json()

    try:
        price = float(data.get("lastPrice", 0))
        volume = float(data.get("quoteVolume", 0))
        change = float(data.get("priceChangePercent", 0))
    except (TypeError, ValueError):
        return None

    return _to_coin_gecko_shape(coingecko_id, price, volume, change)


def _fetch_kraken(coingecko_id: str) -> Optional[Dict[str, Any]]:
    pair = KRAKEN_SYMBOLS.get(coingecko_id)
    if not pair:
        return None

    url = f"{KRAKEN_BASE_URL}/0/public/Ticker"
    params = {"pair": pair}
    response = _safe_get(url, params=params)
    payload = response.json()
    result = payload.get("result", {})
    if not result:
        return None

    key = next(iter(result.keys()), None)
    if not key:
        return None
    ticker = result.get(key, {})

    try:
        price = float(ticker.get("c", [0])[0])
        open_price = float(ticker.get("o", 0))
        volume = float(ticker.get("v", [0])[1])
        change = ((price - open_price) / open_price * 100) if open_price else 0.0
    except (TypeError, ValueError, IndexError):
        return None

    return _to_coin_gecko_shape(coingecko_id, price, volume, change)


def _to_dex_shape(
    coingecko_id: str,
    price: float,
    volume_24h: float,
    price_change_24h: float,
    chain: str = "solana",
    liquidity_usd: float = 0.0,
    pair_address: str = "",
    dex_id: str = "",
) -> Dict[str, Any]:
    return {
        coingecko_id: {
            "usd": price,
            "usd_24h_vol": volume_24h,
            "usd_24h_change": price_change_24h,
            "market_cap": {"usd": 0},
            "chain": chain,
            "liquidity_usd": liquidity_usd,
            "pair_address": pair_address,
            "dex_id": dex_id,
            "source": "dex",
        }
    }


def _fetch_dexscreener(coingecko_id: str, chain: str = "solana") -> Optional[Dict[str, Any]]:
    base_symbol = COINGECKO_ID_TO_BASE.get(coingecko_id)
    if not base_symbol:
        return None

    chain_id = DEXSCRENER_CHAIN_MAP.get(chain, chain)
    url = f"{DEXSCREENER_BASE_URL}/latest/dex/search"
    params = {"q": base_symbol}
    try:
        response = _safe_get(url, params=params)
    except Exception as exc:
        logger.warning("DexScreener fetch failed for %s: %s", coingecko_id, exc)
        return None

    try:
        data = response.json()
    except Exception:
        return None

    pairs = data.get("pairs") or []
    if not pairs:
        return None

    best = None
    best_liq = 0.0
    for p in pairs:
        if p.get("chainId", "").lower() != chain_id.lower():
            continue
        base = p.get("baseToken", {}) or {}
        if base.get("symbol", "").upper() != base_symbol.upper():
            continue
        liq = (p.get("liquidity") or {}).get("usd", 0) or 0
        if liq > best_liq:
            best_liq = liq
            best = p

    if not best:
        return None

    try:
        price = float((best.get("priceUsd") or 0))
        vol_24h = float((best.get("volume") or {}).get("h24", 0) or 0)
        change_24h = float((best.get("priceChange") or {}).get("h24", 0) or 0)
    except (TypeError, ValueError):
        return None

    if best_liq < DEX_SIGNAL_THRESHOLDS["min_liquidity_usd"]:
        return None
    if vol_24h < DEX_SIGNAL_THRESHOLDS["min_volume_24h_usd"]:
        return None

    return _to_dex_shape(
        coingecko_id, price, vol_24h, change_24h,
        chain=chain_id,
        liquidity_usd=best_liq,
        pair_address=best.get("pairAddress", ""),
        dex_id=best.get("dexId", ""),
    )


def fetch_dex_signals(
    coingecko_ids: Iterable[str],
    chain: str = "solana",
    min_composite_score: float = 0.4,
) -> Dict[str, Any]:
    """Fetch DEX market data + signal strength for given CoinGecko IDs.

    Returns dict of {coingecko_id: {price, volume, change, chain, liquidity, signal_strength, source}}.
    Signal strength is a simple heuristic (0-1) based on volume/liquidity ratio.
    """
    results: Dict[str, Any] = {}
    for cg_id in coingecko_ids:
        if not cg_id:
            continue
        try:
            data = _fetch_dexscreener(cg_id, chain=chain)
            if not data or cg_id not in data:
                continue
            entry = data[cg_id]
            liq = entry.get("liquidity_usd", 0)
            vol = entry.get("usd_24h_vol", 0)
            if liq > 0 and vol > 0:
                vol_liq = vol / liq
                entry["signal_strength"] = round(min(vol_liq / 5.0, 1.0), 3)
                entry["meets_signal_threshold"] = entry["signal_strength"] >= min_composite_score
            else:
                entry["signal_strength"] = 0.0
                entry["meets_signal_threshold"] = False
            results[cg_id] = entry
        except Exception as exc:
            logger.warning("DEX signal fetch failed for %s: %s", cg_id, exc)
    return results


def fetch_simple_price(
    ids: Iterable[str],
    vs_currency: str = "usd",
    include_market_cap: bool = True,
    include_24hr_vol: bool = True,
    include_24hr_change: bool = True,
    include_last_updated_at: bool = True,
) -> Dict[str, Any]:
    ids_list = [i for i in ids if i]
    if not ids_list:
        return {}

    results: Dict[str, Any] = {}
    for coingecko_id in ids_list:
        try:
            data = _fetch_binance(coingecko_id)
            if not data:
                data = _fetch_kraken(coingecko_id)
            if not data:
                data = coingecko_fetch_simple_price(
                    ids=[coingecko_id],
                    vs_currency=vs_currency,
                    include_market_cap=include_market_cap,
                    include_24hr_vol=include_24hr_vol,
                    include_24hr_change=include_24hr_change,
                    include_last_updated_at=include_last_updated_at,
                )
            if data and coingecko_id in data:
                results[coingecko_id] = data[coingecko_id]
        except Exception as exc:
            logger.warning("Market data fetch failed for %s: %s", coingecko_id, exc)

    return results


def fetch_simple_price_with_dex(
    ids: Iterable[str],
    vs_currency: str = "usd",
    chain: str = "solana",
    prefer_dex: bool = False,
    include_market_cap: bool = True,
    include_24hr_vol: bool = True,
    include_24hr_change: bool = True,
    include_last_updated_at: bool = True,
) -> Dict[str, Any]:
    """Like fetch_simple_price, optionally preferring DEX sources for early-listing tokens.

    When prefer_dex=True, fetches from DexScreener first (free, no auth, may have
    pre-listing data), then falls back to CEX (Binance/Kraken) and CoinGecko.
    Use this for tokens that may not be on major CEXs yet.
    """
    if prefer_dex:
        cex_results = fetch_simple_price(
            ids, vs_currency=vs_currency,
            include_market_cap=include_market_cap,
            include_24hr_vol=include_24hr_vol,
            include_24hr_change=include_24hr_change,
            include_last_updated_at=include_last_updated_at,
        )
        dex_results = fetch_dex_signals(ids, chain=chain)
        for cg_id, dex_data in dex_results.items():
            if cg_id in cex_results:
                cex_entry = cex_results[cg_id]
                cex_entry["dex_supplement"] = {
                    "liquidity_usd": dex_data.get("liquidity_usd", 0),
                    "signal_strength": dex_data.get("signal_strength", 0),
                    "chain": dex_data.get("chain"),
                    "dex_id": dex_data.get("dex_id"),
                }
            else:
                cex_results[cg_id] = dex_data
        return cex_results
    return fetch_simple_price(
        ids, vs_currency=vs_currency,
        include_market_cap=include_market_cap,
        include_24hr_vol=include_24hr_vol,
        include_24hr_change=include_24hr_change,
        include_last_updated_at=include_last_updated_at,
    )
