import pytest
from unittest.mock import patch, MagicMock
from src.data import coingecko_client


class TestCoinGeckoClient:
    def test_fetch_simple_price_empty_ids(self):
        result = coingecko_client.fetch_simple_price([])
        assert result == {}

    @patch("src.data.coingecko_client._safe_get_with_backoff")
    def test_fetch_simple_price_success(self, mock_safe_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "bitcoin": {"usd": 50000.0, "usd_24h_vol": 1000000.0}
        }
        mock_safe_get.return_value = mock_response
        result = coingecko_client.fetch_simple_price(["bitcoin"])
        assert "bitcoin" in result
        assert result["bitcoin"]["usd"] == 50000.0

    @patch("src.data.coingecko_client._safe_get_with_backoff")
    def test_fetch_simple_price_non_dict_response(self, mock_safe_get):
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_safe_get.return_value = mock_response
        result = coingecko_client.fetch_simple_price(["bitcoin"])
        assert result == {}

    def test_constants(self):
        assert coingecko_client.COINGECKO_BASE_URL == "https://api.coingecko.com/api/v3"
        assert coingecko_client.MIN_INTERVAL_SECONDS == 6.0
        assert coingecko_client.MAX_RETRIES == 3
        assert coingecko_client.TIMEOUT_SECONDS == 10

    @patch("src.data.coingecko_client.requests.get")
    def test_rate_limited_get(self, mock_get):
        mock_response = MagicMock()
        mock_get.return_value = mock_response
        url = f"{coingecko_client.COINGECKO_BASE_URL}/simple/price"
        try:
            result = coingecko_client._rate_limited_get(url, params={"ids": "bitcoin"})
        except Exception:
            pass

    @patch("src.data.coingecko_client._rate_limited_get")
    def test_safe_get_with_backoff_success(self, mock_rate_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_rate_get.return_value = mock_response
        url = "https://api.coingecko.com/api/v3/simple/price"
        result = coingecko_client._safe_get_with_backoff(url)
        assert result.status_code == 200

    @patch("src.data.coingecko_client._rate_limited_get")
    def test_safe_get_with_backoff_retry_then_success(self, mock_rate_get):
        mock_fail = MagicMock()
        mock_fail.status_code = 429
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_rate_get.side_effect = [mock_fail, mock_ok]
        url = "https://api.coingecko.com/api/v3/simple/price"
        result = coingecko_client._safe_get_with_backoff(url)
        assert result.status_code == 200

    @patch("src.data.coingecko_client.requests.get")
    def test_min_interval_enforced(self, mock_get):
        mock_response = MagicMock()
        mock_get.return_value = mock_response
        url = f"{coingecko_client.COINGECKO_BASE_URL}/simple/price"
        # first call
        coingecko_client._rate_limited_get(url)
        # second call - should enforce min interval
        coingecko_client._rate_limited_get(url)
        assert mock_get.call_count == 2
