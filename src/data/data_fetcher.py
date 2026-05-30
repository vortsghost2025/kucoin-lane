"""
Data Fetching Agent
Asynchronously fetches price data, volume, on-chain metrics, and volatility data.
Normalizes all data into a consistent format and implements basic caching.
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime

from ..base_agent import BaseAgent, AgentStatus
from .multi_provider_client import fetch_simple_price


class DataFetchingAgent(BaseAgent):
    """
    Data Fetching Agent: Retrieves market and on-chain data from public APIs.

    Responsibilities:
    - Fetch price data from multiple sources
    - Fetch volume and volatility metrics
    - Fetch on-chain metrics (Solana-focused)
    - Normalize data format
    - Implement caching to reduce API calls
    - Handle API errors gracefully

    APIs Used:
    - Binance Public (free, no auth required)
    - Kraken Public (free, no auth required)
    - CoinGecko (fallback, free, no auth required)
    - DeFiLlama (free, no auth required)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("DataFetchingAgent", config)
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_timeout = config.get("cache_timeout", 300) if config else 300
        self.defillama_base_url = "https://api.llama.fi"

    def _is_cache_valid(self, cache_key: str) -> bool:
        if cache_key not in self.cache:
            return False

        cached_time = self.cache[cache_key].get("timestamp")
        if not cached_time:
            return False

        age = (datetime.utcnow() - cached_time).total_seconds()
        return age < self.cache_timeout

    def _get_coingecko_id(self, trading_pair: str) -> Optional[str]:
        mapping = {
            "SOL": "solana",
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "USDC": "usd-coin",
            "USDT": "tether",
            "RAY": "raydium",
            "ORCA": "orca",
            "COPE": "cope",
        }
        try:
            base_asset = trading_pair.split("/", 1)[0].upper()
            coingecko_id = mapping.get(base_asset)
            if not coingecko_id:
                self.logger.warning(
                    f"No CoinGecko ID found for base asset '{base_asset}' from pair '{trading_pair}'"
                )
            return coingecko_id
        except (AttributeError, IndexError):
            self.logger.error(
                f"Could not parse trading pair format: '{trading_pair}'. Expected format like 'BASE/QUOTE'."
            )
            return None

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self.log_execution_start("fetch_market_data")

        try:
            symbols = input_data.get("symbols", [])
            if not symbols:
                raise ValueError("No symbols provided")

            market_data = {}

            for pair in symbols:
                self.logger.info(f"Fetching data for {pair}")

                parts = pair.split("/")
                if len(parts) != 2:
                    self.logger.warning(f"Invalid pair format: {pair}")
                    continue

                base_symbol, quote_symbol = parts
                coingecko_id = self._get_coingecko_id(base_symbol)

                if not coingecko_id:
                    self.logger.warning(f"Unknown symbol: {base_symbol}")
                    continue

                vs_currency = quote_symbol.lower()
                if vs_currency in {"usdt", "usd"}:
                    vs_currency = "usd"

                cache_key = f"{coingecko_id}_{vs_currency}"
                if self._is_cache_valid(cache_key):
                    self.logger.info(f"Using cached data for {pair}")
                    market_data[pair] = self.cache[cache_key]["data"]
                    continue

                price_data = self._fetch_price_data(coingecko_id, vs_currency)
                if price_data:
                    normalized = self._normalize_data(pair, price_data)
                    market_data[pair] = normalized

                    self.cache[cache_key] = {
                        "data": normalized,
                        "timestamp": datetime.utcnow(),
                    }
                    self.logger.info(
                        f"Fetched {pair}: ${normalized['current_price']:.4f}"
                    )

            if not market_data:
                raise ValueError("Failed to fetch data for any symbol")

            self.log_execution_end("fetch_market_data", success=True)

            return self.create_message(
                action="fetch_market_data",
                success=True,
                data={
                    "market_data": market_data,
                    "symbols_count": len(market_data),
                    "cache_size": len(self.cache),
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

        except Exception as e:
            error_msg = f"Data fetching error: {str(e)}"
            self.set_status(AgentStatus.ERROR, error_msg)
            self.log_execution_end("fetch_market_data", success=False)
            return self.create_message(
                action="fetch_market_data", success=False, error=error_msg
            )

    def _fetch_price_data(
        self, coingecko_id: str, vs_currency: str = "usd"
    ) -> Optional[Dict[str, Any]]:
        try:
            data = fetch_simple_price(ids=[coingecko_id], vs_currency=vs_currency)
            if coingecko_id in data:
                return data[coingecko_id]
            return None
        except Exception as e:
            self.logger.error(f"CoinGecko API error: {str(e)}")
            return None

    def _normalize_data(self, pair: str, price_data: Dict[str, Any]) -> Dict[str, Any]:
        currency = "usd"

        return {
            "pair": pair,
            "current_price": price_data.get(currency, 0),
            "market_cap": price_data.get("market_cap", {}).get(currency, 0),
            "volume_24h": price_data.get("usd_24h_vol", 0),
            "price_change_24h": price_data.get("usd", 0) * price_data.get("usd_24h_change", 0) / 100,
            "price_change_24h_pct": price_data.get("usd_24h_change", 0),
            "last_updated": datetime.utcnow().isoformat(),
            "currency": currency.upper(),
        }

    def clear_cache(self) -> None:
        self.cache.clear()
        self.logger.info("Cache cleared")

    def get_cache_status(self) -> Dict[str, Any]:
        valid_entries = sum(1 for key in self.cache if self._is_cache_valid(key))
        return {
            "total_entries": len(self.cache),
            "valid_entries": valid_entries,
            "timeout_seconds": self.cache_timeout,
        }
