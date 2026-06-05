import pytest
from unittest.mock import patch, MagicMock
from src.data import multi_provider_client as mpc


class TestDexScreenerFetch:
    def test_constants_exist(self):
        assert mpc.DEXSCREENER_BASE_URL == "https://api.dexscreener.com"
        assert mpc.GECKOTERMINAL_BASE_URL == "https://api.geckoterminal.com"
        assert "solana" in mpc.DEXSCRENER_CHAIN_MAP
        assert mpc.DEX_SIGNAL_THRESHOLDS["min_liquidity_usd"] == 50000.0
        assert mpc.DEX_SIGNAL_THRESHOLDS["min_volume_24h_usd"] == 10000.0
        assert mpc.DEX_SIGNAL_THRESHOLDS["min_composite_score"] == 0.4

    def test_dex_chain_map_coverage(self):
        for chain in ["solana", "ethereum", "base", "arbitrum", "bsc"]:
            assert chain in mpc.DEXSCRENER_CHAIN_MAP

    @patch("src.data.multi_provider_client._safe_get")
    def test_fetch_dexscreener_unknown_id(self, mock_safe_get):
        result = mpc._fetch_dexscreener("nonexistent_token")
        assert result is None

    @patch("src.data.multi_provider_client._safe_get")
    def test_fetch_dexscreener_success(self, mock_safe_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "pairs": [
                {
                    "chainId": "solana",
                    "dexId": "raydium",
                    "pairAddress": "0xabc",
                    "baseToken": {"symbol": "SOL"},
                    "priceUsd": "150.50",
                    "volume": {"h24": 1000000.0},
                    "priceChange": {"h24": 5.2},
                    "liquidity": {"usd": 200000.0},
                }
            ]
        }
        mock_safe_get.return_value = mock_response
        result = mpc._fetch_dexscreener("solana")
        assert result is not None
        assert "solana" in result
        entry = result["solana"]
        assert entry["usd"] == 150.50
        assert entry["usd_24h_vol"] == 1000000.0
        assert entry["chain"] == "solana"
        assert entry["liquidity_usd"] == 200000.0
        assert entry["dex_id"] == "raydium"
        assert entry["source"] == "dex"

    @patch("src.data.multi_provider_client._safe_get")
    def test_fetch_dexscreener_picks_highest_liquidity(self, mock_safe_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "pairs": [
                {
                    "chainId": "solana",
                    "dexId": "raydium",
                    "pairAddress": "0x111",
                    "baseToken": {"symbol": "SOL"},
                    "priceUsd": "150.50",
                    "volume": {"h24": 100000.0},
                    "liquidity": {"usd": 60000.0},
                },
                {
                    "chainId": "solana",
                    "dexId": "orca",
                    "pairAddress": "0x222",
                    "baseToken": {"symbol": "SOL"},
                    "priceUsd": "150.55",
                    "volume": {"h24": 200000.0},
                    "liquidity": {"usd": 500000.0},
                },
            ]
        }
        mock_safe_get.return_value = mock_response
        result = mpc._fetch_dexscreener("solana")
        assert result["solana"]["pair_address"] == "0x222"
        assert result["solana"]["dex_id"] == "orca"
        assert result["solana"]["liquidity_usd"] == 500000.0

    @patch("src.data.multi_provider_client._safe_get")
    def test_fetch_dexscreener_wrong_chain_filtered(self, mock_safe_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "pairs": [
                {
                    "chainId": "ethereum",
                    "baseToken": {"symbol": "SOL"},
                    "priceUsd": "150.50",
                    "volume": {"h24": 100000.0},
                    "liquidity": {"usd": 200000.0},
                }
            ]
        }
        mock_safe_get.return_value = mock_response
        result = mpc._fetch_dexscreener("solana", chain="solana")
        assert result is None

    @patch("src.data.multi_provider_client._safe_get")
    def test_fetch_dexscreener_low_liquidity_filtered(self, mock_safe_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "pairs": [
                {
                    "chainId": "solana",
                    "baseToken": {"symbol": "SOL"},
                    "priceUsd": "150.50",
                    "volume": {"h24": 100000.0},
                    "liquidity": {"usd": 1000.0},
                }
            ]
        }
        mock_safe_get.return_value = mock_response
        result = mpc._fetch_dexscreener("solana")
        assert result is None

    @patch("src.data.multi_provider_client._safe_get")
    def test_fetch_dexscreener_low_volume_filtered(self, mock_safe_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "pairs": [
                {
                    "chainId": "solana",
                    "baseToken": {"symbol": "SOL"},
                    "priceUsd": "150.50",
                    "volume": {"h24": 100.0},
                    "liquidity": {"usd": 200000.0},
                }
            ]
        }
        mock_safe_get.return_value = mock_response
        result = mpc._fetch_dexscreener("solana")
        assert result is None

    @patch("src.data.multi_provider_client._safe_get")
    def test_fetch_dexscreener_empty_pairs(self, mock_safe_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"pairs": []}
        mock_safe_get.return_value = mock_response
        result = mpc._fetch_dexscreener("solana")
        assert result is None

    @patch("src.data.multi_provider_client._safe_get")
    def test_fetch_dexscreener_network_error(self, mock_safe_get):
        mock_safe_get.side_effect = Exception("Network down")
        result = mpc._fetch_dexscreener("solana")
        assert result is None

    def test_to_dex_shape(self):
        result = mpc._to_dex_shape("solana", 150.0, 1000000.0, 5.0, chain="solana", liquidity_usd=200000.0, pair_address="0xabc", dex_id="raydium")
        assert "solana" in result
        entry = result["solana"]
        assert entry["usd"] == 150.0
        assert entry["usd_24h_vol"] == 1000000.0
        assert entry["usd_24h_change"] == 5.0
        assert entry["chain"] == "solana"
        assert entry["liquidity_usd"] == 200000.0
        assert entry["pair_address"] == "0xabc"
        assert entry["dex_id"] == "raydium"
        assert entry["source"] == "dex"


class TestFetchDexSignals:
    @patch("src.data.multi_provider_client._fetch_dexscreener")
    def test_empty_ids(self, mock_fetch):
        result = mpc.fetch_dex_signals([])
        assert result == {}
        mock_fetch.assert_not_called()

    @patch("src.data.multi_provider_client._fetch_dexscreener")
    def test_filters_none_ids(self, mock_fetch):
        result = mpc.fetch_dex_signals(["", None, "solana"])
        assert mock_fetch.call_count == 1
        mock_fetch.assert_called_with("solana", chain="solana")

    @patch("src.data.multi_provider_client._fetch_dexscreener")
    def test_signal_strength_calculation(self, mock_fetch):
        mock_fetch.return_value = {
            "solana": {
                "usd": 150.0,
                "usd_24h_vol": 500000.0,
                "liquidity_usd": 200000.0,
                "chain": "solana",
            }
        }
        result = mpc.fetch_dex_signals(["solana"])
        entry = result["solana"]
        assert entry["signal_strength"] == round(min(500000.0 / 200000.0 / 5.0, 1.0), 3)
        assert entry["signal_strength"] == 0.5
        assert entry["meets_signal_threshold"] is True

    @patch("src.data.multi_provider_client._fetch_dexscreener")
    def test_signal_strength_below_threshold(self, mock_fetch):
        mock_fetch.return_value = {
            "solana": {
                "usd": 150.0,
                "usd_24h_vol": 10000.0,
                "liquidity_usd": 100000.0,
                "chain": "solana",
            }
        }
        result = mpc.fetch_dex_signals(["solana"])
        assert result["solana"]["signal_strength"] < 0.4
        assert result["solana"]["meets_signal_threshold"] is False

    @patch("src.data.multi_provider_client._fetch_dexscreener")
    def test_zero_liquidity_signal_zero(self, mock_fetch):
        mock_fetch.return_value = {
            "solana": {
                "usd": 150.0,
                "usd_24h_vol": 100000.0,
                "liquidity_usd": 0,
                "chain": "solana",
            }
        }
        result = mpc.fetch_dex_signals(["solana"])
        assert result["solana"]["signal_strength"] == 0.0
        assert result["solana"]["meets_signal_threshold"] is False

    @patch("src.data.multi_provider_client._fetch_dexscreener")
    def test_returns_none_filtered(self, mock_fetch):
        mock_fetch.return_value = None
        result = mpc.fetch_dex_signals(["solana"])
        assert result == {}

    @patch("src.data.multi_provider_client._fetch_dexscreener")
    def test_exception_handled(self, mock_fetch):
        mock_fetch.side_effect = Exception("API down")
        result = mpc.fetch_dex_signals(["solana"])
        assert result == {}


class TestFetchSimplePriceWithDex:
    @patch("src.data.multi_provider_client.fetch_simple_price")
    def test_prefer_dex_false_uses_cex(self, mock_cex):
        mock_cex.return_value = {"solana": {"usd": 150.0}}
        result = mpc.fetch_simple_price_with_dex(["solana"], prefer_dex=False)
        assert result == {"solana": {"usd": 150.0}}

    @patch("src.data.multi_provider_client.fetch_dex_signals")
    @patch("src.data.multi_provider_client.fetch_simple_price")
    def test_prefer_dex_true_supplements(self, mock_cex, mock_dex):
        mock_cex.return_value = {"solana": {"usd": 150.0, "source": "cex"}}
        mock_dex.return_value = {
            "solana": {
                "usd": 151.0,
                "liquidity_usd": 200000.0,
                "signal_strength": 0.5,
                "chain": "solana",
                "dex_id": "raydium",
            }
        }
        result = mpc.fetch_simple_price_with_dex(["solana"], prefer_dex=True)
        assert result["solana"]["source"] == "cex"
        assert "dex_supplement" in result["solana"]
        assert result["solana"]["dex_supplement"]["liquidity_usd"] == 200000.0

    @patch("src.data.multi_provider_client.fetch_dex_signals")
    @patch("src.data.multi_provider_client.fetch_simple_price")
    def test_prefer_dex_true_adds_dex_only(self, mock_cex, mock_dex):
        mock_cex.return_value = {"bitcoin": {"usd": 50000.0}}
        mock_dex.return_value = {
            "newtoken": {
                "usd": 0.001,
                "liquidity_usd": 100000.0,
                "signal_strength": 0.3,
                "chain": "solana",
            }
        }
        result = mpc.fetch_simple_price_with_dex(["bitcoin", "newtoken"], prefer_dex=True)
        assert "bitcoin" in result
        assert "newtoken" in result
        assert result["newtoken"]["chain"] == "solana"
