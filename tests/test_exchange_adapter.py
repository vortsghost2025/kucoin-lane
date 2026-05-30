"""Tests for exchange_adapter.py - ABC contract, KuCoinAdapter static methods, factory."""

import os
import pytest
from unittest.mock import patch, MagicMock

from src.execution.exchange_adapter import (
    ExchangeAdapter,
    KuCoinAdapter,
    create_exchange_adapter,
)


class TestExchangeAdapterABC:
    """Verify the ABC cannot be instantiated and enforces abstract methods."""

    def test_cannot_instantiate_abc_directly(self):
        with pytest.raises(TypeError, match="abstract method"):
            ExchangeAdapter("test", "https://example.com", "key", "secret")

    def test_concrete_subclass_must_implement_all_abstracts(self):
        class IncompleteAdapter(ExchangeAdapter):
            def get_balance(self) -> dict:
                return {}

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteAdapter("test", "https://example.com", "key", "secret")

    def test_concrete_subclass_with_all_methods_instantiable(self):
        class StubAdapter(ExchangeAdapter):
            def get_balance(self) -> dict:
                return {}

            def place_order(self, symbol, side, qty, price=None) -> dict:
                return {}

            def cancel_order(self, symbol, order_id) -> dict:
                return {}

            def get_order(self, symbol, order_id) -> dict:
                return {}

            def get_ticker(self, symbol) -> dict:
                return {}

            def get_klines(self, symbol, interval="5min", start=None, end=None) -> list:
                return []

            def borrow(self, asset, amount) -> dict:
                return {}

            def repay(self, asset, amount) -> dict:
                return {}

            def get_margin_info(self) -> dict:
                return {}

        adapter = StubAdapter("stub", "https://stub.com", "key", "secret")
        assert adapter.exchange_name == "stub"
        assert adapter.base_url == "https://stub.com"
        assert adapter.api_key == "key"
        assert adapter.api_secret == "secret"
        assert adapter.session is not None


class TestKuCoinAdapterStaticMethods:
    """Test static helper methods that don't require API connection."""

    def test_format_symbol_replaces_slash(self):
        assert KuCoinAdapter._format_symbol("BTC/USDT") == "BTC-USDT"

    def test_format_symbol_no_slash(self):
        assert KuCoinAdapter._format_symbol("BTC-USDT") == "BTC-USDT"

    def test_format_symbol_empty(self):
        assert KuCoinAdapter._format_symbol("") == ""

    def test_round_size_sol(self):
        assert KuCoinAdapter._round_size("SOL-USDT", 1.2345) == 1.2

    def test_round_size_btc(self):
        assert KuCoinAdapter._round_size("BTC-USDT", 0.00015678) == 0.0002

    def test_round_size_eth(self):
        assert KuCoinAdapter._round_size("ETH-USDT", 0.12345) == 0.123

    def test_round_size_unknown_defaults_to_2dp(self):
        assert KuCoinAdapter._round_size("DOGE-USDT", 123.456) == 123.46

    def test_round_size_sanity_precisions(self):
        assert KuCoinAdapter._round_size("SOL-USDT", 10.0) == 10.0
        assert KuCoinAdapter._round_size("BTC-USDT", 1.0) == 1.0


class TestKuCoinAdapterInit:
    """Test initialization paths (mocked SDK)."""

    @patch("src.execution.exchange_adapter.KuCoinAdapter.__init__", return_value=None)
    def test_init_sets_passphrase(self, mock_init):
        adapter = KuCoinAdapter.__new__(KuCoinAdapter)
        adapter.passphrase = "mypass"
        assert adapter.passphrase == "mypass"

    @patch.dict(os.environ, {"KUCOIN_USE_SANDBOX": "true"})
    def test_sandbox_url_selected(self):
        with patch("src.execution.exchange_adapter.KuCoinAdapter._test_connection"):
            with patch("kucoin.client.Client") as MockClient:
                MockClient.return_value = MagicMock()
                adapter = KuCoinAdapter.__new__(KuCoinAdapter)
                adapter.exchange_name = "kucoin"
                adapter.base_url = "https://openapi-sandbox.kucoin.com"
                adapter.api_key = "k"
                adapter.api_secret = "s"
                adapter.passphrase = "p"
                adapter.session = MagicMock()
                assert "sandbox" in adapter.base_url

    @patch.dict(os.environ, {"KUCOIN_USE_SANDBOX": "false"})
    def test_live_url_selected(self):
        with patch("src.execution.exchange_adapter.KuCoinAdapter._test_connection"):
            with patch("kucoin.client.Client") as MockClient:
                MockClient.return_value = MagicMock()
                adapter = KuCoinAdapter.__new__(KuCoinAdapter)
                adapter.exchange_name = "kucoin"
                adapter.base_url = "https://openapi-v2.kucoin.com"
                adapter.api_key = "k"
                adapter.api_secret = "s"
                adapter.passphrase = "p"
                adapter.session = MagicMock()
                assert "openapi-v2" in adapter.base_url

    def test_import_error_raises_runtime_error(self):
        with patch.dict("sys.modules", {"kucoin": None, "kucoin.client": None}):
            with pytest.raises(RuntimeError, match="kucoin-python not installed"):
                with patch.dict(os.environ, {"KUCOIN_API_KEY": "k", "KUCOIN_API_SECRET": "s", "KUCOIN_API_PASSPHRASE": "p"}):
                    KuCoinAdapter("k", "s", "p")


class TestCreateExchangeAdapterFactory:
    """Test the factory function."""

    def test_missing_env_vars_raises_value_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="KuCoin API credentials missing"):
                create_exchange_adapter()

    @patch("src.execution.exchange_adapter.KuCoinAdapter")
    def test_factory_passes_credentials(self, MockAdapter):
        MockAdapter.return_value = MagicMock()
        with patch.dict(
            os.environ,
            {
                "KUCOIN_API_KEY": "testkey",
                "KUCOIN_API_SECRET": "testsecret",
                "KUCOIN_API_PASSPHRASE": "testphrase",
            },
        ):
            adapter = create_exchange_adapter()
            MockAdapter.assert_called_once_with(
                api_key="testkey",
                api_secret="testsecret",
                passphrase="testphrase",
            )
