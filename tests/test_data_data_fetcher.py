import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from src.data.data_fetcher import DataFetchingAgent


class TestDataFetchingAgent:
    @pytest.fixture
    def config(self):
        return {"cache_timeout": 60}

    @pytest.fixture
    def agent(self, config):
        return DataFetchingAgent(config)

    def test_init(self, agent):
        assert agent.agent_name == "DataFetchingAgent"
        assert agent.cache_timeout == 60
        assert agent.cache == {}

    def test_init_no_config(self):
        agent = DataFetchingAgent()
        assert agent.cache_timeout == 300

    def test_is_cache_valid_no_entry(self, agent):
        assert agent._is_cache_valid("missing_key") is False

    def test_is_cache_valid_expired(self, agent):
        agent.cache["test"] = {
            "data": {"price": 100},
            "timestamp": datetime.utcnow() - timedelta(seconds=120),
        }
        assert agent._is_cache_valid("test") is False

    def test_is_cache_valid_fresh(self, agent):
        agent.cache["test"] = {
            "data": {"price": 100},
            "timestamp": datetime.utcnow(),
        }
        assert agent._is_cache_valid("test") is True

    def test_get_coingecko_id_known(self, agent):
        assert agent._get_coingecko_id("SOL/USDT") == "solana"
        assert agent._get_coingecko_id("BTC/USDT") == "bitcoin"
        assert agent._get_coingecko_id("ETH/USDT") == "ethereum"
        assert agent._get_coingecko_id("USDC/USDT") == "usd-coin"

    def test_get_coingecko_id_unknown(self, agent):
        assert agent._get_coingecko_id("XYZ/USDT") is None

    def test_get_coingecko_id_invalid_format(self, agent):
        assert agent._get_coingecko_id("INVALID") is None

    def test_execute_no_symbols(self, agent):
        result = agent.execute({"symbols": []})
        assert result["success"] is False

    @patch("src.data.data_fetcher.fetch_simple_price")
    def test_execute_fetch_success(self, mock_fetch, agent):
        mock_fetch.return_value = {
            "solana": {
                "usd": 150.0,
                "usd_24h_vol": 1000000.0,
                "usd_24h_change": 5.0,
                "market_cap": {"usd": 50000000000},
            }
        }
        result = agent.execute({"symbols": ["SOL/USDT"]})
        assert result["success"] is True
        data = result["data"]["market_data"]
        assert "SOL/USDT" in data
        assert data["SOL/USDT"]["current_price"] == 150.0

    @patch("src.data.data_fetcher.fetch_simple_price")
    def test_execute_caches_data(self, mock_fetch, agent):
        mock_fetch.return_value = {
            "solana": {
                "usd": 150.0,
                "usd_24h_vol": 1000000.0,
                "usd_24h_change": 5.0,
                "market_cap": {"usd": 50000000000},
            }
        }
        agent.execute({"symbols": ["SOL/USDT"]})
        assert "solana_usd" in agent.cache
        # second call should use cache
        mock_fetch.reset_mock()
        agent.execute({"symbols": ["SOL/USDT"]})
        mock_fetch.assert_not_called()

    @patch("src.data.data_fetcher.fetch_simple_price")
    def test_execute_fetch_failure(self, mock_fetch, agent):
        mock_fetch.side_effect = Exception("API error")
        result = agent.execute({"symbols": ["SOL/USDT"]})
        assert result["success"] is False

    def test_clear_cache(self, agent):
        agent.cache["test"] = {"data": {}, "timestamp": datetime.utcnow()}
        agent.clear_cache()
        assert agent.cache == {}

    def test_get_cache_status(self, agent):
        status = agent.get_cache_status()
        assert status["total_entries"] == 0
        assert status["timeout_seconds"] == 60

    def test_get_cache_status_with_entries(self, agent):
        agent.cache["test"] = {
            "data": {"price": 100},
            "timestamp": datetime.utcnow(),
        }
        status = agent.get_cache_status()
        assert status["total_entries"] == 1
        assert status["valid_entries"] == 1

    def test_normalize_data(self, agent):
        price_data = {
            "usd": 100.0,
            "market_cap": {"usd": 50000},
            "usd_24h_vol": 1000.0,
            "usd_24h_change": 2.5,
        }
        normalized = agent._normalize_data("SOL/USDT", price_data)
        assert normalized["pair"] == "SOL/USDT"
        assert normalized["current_price"] == 100.0
        assert normalized["market_cap"] == 50000
        assert normalized["currency"] == "USD"
