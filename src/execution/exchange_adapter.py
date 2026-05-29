"""
Unified exchange adapter for multi-exchange support.
Abstracts KuCoin and Binance (testnet/live) behind a common interface.
"""

import os
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

import requests
import hmac
import hashlib
import base64
import time
import json
from urllib.parse import urlencode


class ExchangeAdapter(ABC):
    """Base class for exchange-agnostic operations."""

    def __init__(
        self, exchange_name: str, base_url: str, api_key: str, api_secret: str, **kwargs
    ) -> None:
        self.exchange_name = exchange_name
        self.base_url = base_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()

    @abstractmethod
    def get_balance(self) -> Dict[str, float]:
        pass

    @abstractmethod
    def place_order(
        self, symbol: str, side: str, qty: float, price: Optional[float] = None
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_ticker(self, symbol: str) -> Dict[str, float]:
        pass

    @abstractmethod
    def borrow(self, asset: str, amount: float) -> Dict[str, Any]:
        pass

    @abstractmethod
    def repay(self, asset: str, amount: float) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_margin_info(self) -> Dict[str, Any]:
        pass


class KuCoinAdapter(ExchangeAdapter):
    """KuCoin exchange adapter using python-kucoin SDK."""

    def __init__(self, api_key: str, api_secret: str, passphrase: str) -> None:
        try:
            from kucoin.client import Client as KuCoinClient
        except ImportError:
            raise RuntimeError(
                "kucoin-python not installed. Run: pip install python-kucoin"
            )

        use_sandbox = os.getenv("KUCOIN_USE_SANDBOX", "true").lower() == "true"
        base_url = (
            "https://openapi-sandbox.kucoin.com"
            if use_sandbox
            else "https://openapi-v2.kucoin.com"
        )

        super().__init__(
            exchange_name="kucoin",
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
        )
        self.passphrase = passphrase
        self.kucoin_client = KuCoinClient(
            key=api_key,
            secret=api_secret,
            passphrase=passphrase,
            sandbox=use_sandbox,
        )
        self._test_connection()

    def _test_connection(self) -> None:
        try:
            self.kucoin_client.get_accounts()
        except Exception as e:
            raise RuntimeError(f"KuCoin API connection failed: {e}")

    @staticmethod
    def _format_symbol(pair: str) -> str:
        return pair.replace("/", "-")

    @staticmethod
    def _round_size(symbol: str, size: float) -> float:
        if "SOL" in symbol:
            return round(size, 1)
        elif "BTC" in symbol:
            return round(size, 4)
        elif "ETH" in symbol:
            return round(size, 3)
        return round(size, 2)

    def get_balance(self) -> Dict[str, float]:
        accounts = self.kucoin_client.get_accounts()
        balance = {}
        for acct in accounts:
            asset = acct.get("currency", "")
            available = float(acct.get("available", 0))
            if available > 0:
                balance[asset] = available
        return balance

    def place_order(
        self, symbol: str, side: str, qty: float, price: Optional[float] = None
    ) -> Dict[str, Any]:
        kucoin_symbol = self._format_symbol(symbol)
        qty = self._round_size(kucoin_symbol, qty)

        if price is None:
            order = self.kucoin_client.create_market_order(
                symbol=kucoin_symbol,
                side=side,
                size=str(qty),
            )
        else:
            order = self.kucoin_client.create_limit_order(
                symbol=kucoin_symbol,
                side=side,
                price=str(price),
                size=str(qty),
            )

        order_id = order.get("orderId", "")
        return {"orderId": order_id, "status": "submitted", "symbol": kucoin_symbol}

    def place_stop_loss(
        self,
        symbol: str,
        side: str,
        qty: float,
        stop_price: float,
        limit_price: float,
    ) -> Dict[str, Any]:
        kucoin_symbol = self._format_symbol(symbol)
        qty = self._round_size(kucoin_symbol, qty)

        order = self.kucoin_client.create_stop_order(
            symbol=kucoin_symbol,
            side=side,
            type="limit",
            stop="loss",
            stop_price=str(round(stop_price, 2)),
            size=str(qty),
            price=str(round(limit_price, 2)),
        )
        return {"orderId": order.get("orderId", ""), "status": "submitted"}

    def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        result = self.kucoin_client.cancel_order(order_id)
        return {"orderId": order_id, "status": "cancelled", "result": result}

    def get_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        order = self.kucoin_client.get_order(order_id)
        return order

    def get_ticker(self, symbol: str) -> Dict[str, float]:
        kucoin_symbol = self._format_symbol(symbol)
        ticker = self.kucoin_client.get_ticker(kucoin_symbol)
        return {
            "bid": float(ticker.get("bestBid", 0)),
            "ask": float(ticker.get("bestAsk", 0)),
            "last": float(ticker.get("price", 0)),
        }

    def borrow(self, asset: str, amount: float) -> Dict[str, Any]:
        result = self.kucoin_client.create_borrow_order(
            currency=asset,
            size=str(amount),
        )
        return result

    def repay(self, asset: str, amount: float) -> Dict[str, Any]:
        result = self.kucoin_client.create_repay_order(
            currency=asset,
            size=str(amount),
        )
        return result

    def get_margin_info(self) -> Dict[str, Any]:
        accounts = self.kucoin_client.get_accounts(account_type="margin")
        return {"accounts": accounts}


def create_exchange_adapter() -> KuCoinAdapter:
    api_key = os.getenv("KUCOIN_API_KEY", "")
    api_secret = os.getenv("KUCOIN_API_SECRET", "")
    passphrase = os.getenv("KUCOIN_API_PASSPHRASE", "")

    if not all([api_key, api_secret, passphrase]):
        raise ValueError(
            "KuCoin API credentials missing. Set KUCOIN_API_KEY, "
            "KUCOIN_API_SECRET, and KUCOIN_API_PASSPHRASE environment variables."
        )

    return KuCoinAdapter(
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
    )
