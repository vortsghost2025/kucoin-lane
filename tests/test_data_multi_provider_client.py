import pytest
from unittest.mock import patch, MagicMock
from src.data import multi_provider_client


class TestMultiProviderClient:
    def test_fetch_simple_price_empty_ids(self):
        result = multi_provider_client.fetch_simple_price([])
        assert result == {}

    @patch("src.data.multi_provider_client._fetch_binance")
    def test_fetch_simple_price_uses_binance_first(self, mock_binance):
        mock_binance.return_value = {
            "bitcoin": {"usd": 50000.0, "usd_24h_vol": 0, "usd_24h_change": 0, "market_cap": {"usd": 0}}
        }
        result = multi_provider_client.fetch_simple_price(["bitcoin"])
        assert result["bitcoin"]["usd"] == 50000.0
        mock_binance.assert_called_once_with("bitcoin")

    @patch("src.data.multi_provider_client._fetch_binance")
    @patch("src.data.multi_provider_client._fetch_kraken")
    def test_fetch_simple_price_falls_back_to_kraken(self, mock_kraken, mock_binance):
        mock_binance.return_value = None
        mock_kraken.return_value = {
            "bitcoin": {"usd": 49000.0, "usd_24h_vol": 0, "usd_24h_change": 0, "market_cap": {"usd": 0}}
        }
        result = multi_provider_client.fetch_simple_price(["bitcoin"])
        assert result["bitcoin"]["usd"] == 49000.0

    @patch("src.data.multi_provider_client._fetch_binance")
    @patch("src.data.multi_provider_client._fetch_kraken")
    @patch("src.data.multi_provider_client.coingecko_fetch_simple_price")
    def test_fetch_simple_price_falls_back_to_coingecko(self, mock_cg, mock_kraken, mock_binance):
        mock_binance.return_value = None
        mock_kraken.return_value = None
        mock_cg.return_value = {
            "bitcoin": {"usd": 48000.0, "usd_24h_vol": 0, "usd_24h_change": 0, "market_cap": {"usd": 0}}
        }
        result = multi_provider_client.fetch_simple_price(["bitcoin"])
        assert result["bitcoin"]["usd"] == 48000.0

    @patch("src.data.multi_provider_client.requests.get")
    def test_fetch_binance_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "lastPrice": "50000.0",
            "quoteVolume": "1000000.0",
            "priceChange": "100.0",
        }
        mock_get.return_value = mock_response
        result = multi_provider_client._fetch_binance("bitcoin")
        assert result is not None
        assert result["bitcoin"]["usd"] == 50000.0

    @patch("src.data.multi_provider_client.requests.get")
    def test_fetch_binance_unknown_symbol(self, mock_get):
        result = multi_provider_client._fetch_binance("unknown-coin")
        assert result is None
        mock_get.assert_not_called()

    @patch("src.data.multi_provider_client.requests.get")
    def test_fetch_kraken_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "XBTUSD": {
                    "c": ["50000.0"],
                    "o": "49000.0",
                    "v": ["1000", "5000"],
                }
            }
        }
        mock_get.return_value = mock_response
        result = multi_provider_client._fetch_kraken("bitcoin")
        assert result is not None
        assert result["bitcoin"]["usd"] == 50000.0

    @patch("src.data.multi_provider_client.requests.get")
    def test_fetch_kraken_unknown_symbol(self, mock_get):
        result = multi_provider_client._fetch_kraken("unknown-coin")
        assert result is None
        mock_get.assert_not_called()

    @patch("src.data.multi_provider_client.requests.get")
    def test_fetch_kraken_empty_result(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": {}}
        mock_get.return_value = mock_response
        result = multi_provider_client._fetch_kraken("bitcoin")
        assert result is None

    def test_to_coin_gecko_shape(self):
        result = multi_provider_client._to_coin_gecko_shape("bitcoin", 50000.0, 1000.0, 100.0)
        assert result["bitcoin"]["usd"] == 50000.0
        assert result["bitcoin"]["usd_24h_vol"] == 1000.0
        assert result["bitcoin"]["usd_24h_change"] == 100.0

    def test_mappings(self):
        assert multi_provider_client.COINGECKO_ID_TO_BASE["bitcoin"] == "BTC"
        assert multi_provider_client.COINGECKO_ID_TO_BASE["solana"] == "SOL"
        assert multi_provider_client.BINANCE_SYMBOLS["bitcoin"] == "BTCUSDT"
        assert multi_provider_client.KRAKEN_SYMBOLS["bitcoin"] == "XBTUSD"
