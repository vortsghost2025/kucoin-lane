import pytest
from unittest.mock import patch, MagicMock
from src.data.dex_intelligence import scanner


class TestDexScanner:
    def test_init_default_chains(self):
        s = scanner.DexScanner()
        assert s.chains == ["solana"]
        assert s.ds is not None
        assert s.gt is not None
        assert s.pf is None
        assert s.scorer is not None

    def test_init_with_chains(self):
        s = scanner.DexScanner(chains=["solana", "base"])
        assert s.chains == ["solana", "base"]

    def test_init_with_rpc(self):
        s = scanner.DexScanner(chains=["solana"], rpc_url="https://api.mainnet-beta.solana.com")
        assert s.pf is not None

    @patch("src.data.dex_intelligence.scanner.DexScreenerProvider")
    def test_scan_trending(self, mock_ds_class):
        mock_ds = MagicMock()
        mock_ds.trending_tokens.return_value = [
            {"tokenAddress": "0xabc"},
            {"tokenAddress": "0xdef"},
        ]
        mock_ds.get_token.return_value = {
            "baseToken": {"symbol": "BONK"},
            "quoteToken": {"symbol": "USDC"},
            "chainId": "solana",
            "volume": {"h24": 1000000, "h6": 200000, "h1": 50000},
            "liquidity": {"usd": 500000},
            "marketCap": 2000000,
            "priceUsd": "0.000001",
            "txns": {"h24": {"buys": 100, "sells": 50}, "h1": {"buys": 10, "sells": 5}},
            "pairCreatedAt": 1715000000000,
        }
        bonk_pair = {
            "base_token": {"symbol": "BONK"},
            "quote_token": {"symbol": "USDC"},
            "chain": "solana",
            "volume_24h": 1000000,
            "liquidity_usd": 500000,
            "market_cap": 2000000,
            "buys_24h": 100,
            "sells_24h": 50,
        }
        mock_ds_class.normalize_pair = staticmethod(lambda pair: bonk_pair)
        mock_ds_class.return_value = mock_ds
        s = scanner.DexScanner()
        results = s.scan_trending(chain="solana")
        assert len(results) == 2
        assert results[0]["base_token"]["symbol"] == "BONK"

    @patch("src.data.dex_intelligence.scanner.DexScreenerProvider")
    def test_scan_trending_handles_missing_token_addr(self, mock_ds_class):
        mock_ds = MagicMock()
        mock_ds.trending_tokens.return_value = [
            {"tokenAddress": "0xabc"},
            {"tokenAddress": None},
            {},
        ]
        mock_ds.get_token.return_value = {
            "baseToken": {"symbol": "X"},
            "quoteToken": {"symbol": "Y"},
            "chainId": "solana",
            "volume": {"h24": 1000},
            "liquidity": {"usd": 10000},
        }
        x_pair = {
            "base_token": {"symbol": "X"},
            "quote_token": {"symbol": "Y"},
            "chain": "solana",
            "volume_24h": 1000,
            "liquidity_usd": 10000,
        }
        mock_ds_class.normalize_pair = staticmethod(lambda pair: x_pair)
        mock_ds_class.return_value = mock_ds
        s = scanner.DexScanner()
        results = s.scan_trending(chain="solana")
        assert len(results) == 1

    @patch("src.data.dex_intelligence.scanner.DexScreenerProvider")
    def test_scan_trending_error_handled(self, mock_ds_class):
        mock_ds = MagicMock()
        mock_ds.trending_tokens.side_effect = Exception("API down")
        mock_ds_class.return_value = mock_ds
        s = scanner.DexScanner()
        results = s.scan_trending(chain="solana")
        assert results == []

    @patch("src.data.dex_intelligence.scanner.GeckoTerminalProvider")
    def test_scan_new_pools(self, mock_gt_class):
        mock_gt = MagicMock()
        mock_gt.new_pools.return_value = [
            {"id": "1", "attributes": {"name": "TOKENX/SOL", "volume_usd_24h": "50000"}},
        ]
        mock_gt.normalize_pool.return_value = {
            "name": "TOKENX/SOL",
            "chain": "solana",
            "volume_usd_24h": 50000,
        }
        mock_gt_class.return_value = mock_gt
        s = scanner.DexScanner()
        results = s.scan_new_pools(chain="solana")
        assert len(results) == 1

    @patch("src.data.dex_intelligence.scanner.DexScreenerProvider")
    def test_scan_search(self, mock_ds_class):
        mock_ds = MagicMock()
        mock_ds.search.return_value = [
            {"baseToken": {"symbol": "BONK"}, "quoteToken": {"symbol": "USDC"}},
        ]
        bonk_pair = {
            "base_token": {"symbol": "BONK"},
            "quote_token": {"symbol": "USDC"},
        }
        mock_ds_class.normalize_pair = staticmethod(lambda pair: bonk_pair)
        mock_ds_class.return_value = mock_ds
        s = scanner.DexScanner()
        results = s.scan_search("BONK")
        assert len(results) == 1

    def test_scan_pumpfun_no_rpc(self):
        s = scanner.DexScanner()
        results = s.scan_pumpfun()
        assert results == []

    @patch("src.data.dex_intelligence.scanner.PumpFunTracker")
    def test_scan_pumpfun_with_rpc(self, mock_pf_class):
        mock_pf = MagicMock()
        mock_pf.get_recent_tokens.return_value = [
            {"symbol": "PUMP1", "graduated": True, "bonding_progress_pct": 100},
            {"symbol": "PUMP2", "graduated": False, "bonding_progress_pct": 85},
        ]
        mock_pf_class.return_value = mock_pf
        s = scanner.DexScanner(rpc_url="https://api.mainnet-beta.solana.com")
        results = s.scan_pumpfun(limit=10)
        assert len(results) == 2

    @patch("src.data.dex_intelligence.scanner.DexScreenerProvider")
    @patch("src.data.dex_intelligence.scanner.GeckoTerminalProvider")
    def test_full_scan(self, mock_gt_class, mock_ds_class):
        mock_ds = MagicMock()
        mock_ds.trending_tokens.return_value = [{"tokenAddress": "0xabc"}]
        mock_ds.get_token.return_value = {"raw": "raw_data"}
        strong_pair = {
            "base_token": {"symbol": "STRONG"}, "quote_token": {"symbol": "USDC"},
            "chain": "solana", "volume_24h": 1000000, "liquidity_usd": 500000,
            "market_cap": 2000000, "buys_24h": 800, "sells_24h": 200,
            "buys_1h": 40, "sells_1h": 10, "graduated": True,
        }
        mock_ds_class.normalize_pair = staticmethod(lambda pair: strong_pair)
        mock_ds_class.return_value = mock_ds
        mock_gt = MagicMock()
        mock_gt.new_pools.return_value = []
        mock_gt_class.return_value = mock_gt
        s = scanner.DexScanner()
        result = s.full_scan(chain="solana")
        assert "scan_time" in result
        assert result["chain"] == "solana"
        assert result["trending_count"] == 1
        assert result["new_pools_count"] == 0
        assert result["pumpfun_count"] == 0
        assert "summary" in result
        assert "elapsed_seconds" in result

    @patch("src.data.dex_intelligence.scanner.DexScreenerProvider")
    @patch("src.data.dex_intelligence.scanner.GeckoTerminalProvider")
    def test_full_scan_empty(self, mock_gt_class, mock_ds_class):
        mock_ds = MagicMock()
        mock_ds.trending_tokens.return_value = []
        mock_ds_class.return_value = mock_ds
        mock_gt = MagicMock()
        mock_gt.new_pools.return_value = []
        mock_gt_class.return_value = mock_gt
        s = scanner.DexScanner()
        result = s.full_scan(chain="solana")
        assert result["trending_count"] == 0
        assert result["new_pools_count"] == 0
        assert result["summary"] == "No actionable signals detected"
        assert result["top_trending"] == []

    def test_build_summary_strong_buys(self):
        trending = [
            {"signal": "STRONG_BUY"},
            {"signal": "STRONG_BUY"},
            {"signal": "BUY"},
        ]
        summary = scanner.DexScanner._build_summary(trending, [], [])
        assert "2 STRONG_BUY" in summary
        assert "1 BUY" in summary

    def test_build_summary_pumpfun_graduations(self):
        trending = []
        new = []
        pumpfun = [{"graduated": True}, {"graduated": True, "bonding_progress_pct": 100}]
        summary = scanner.DexScanner._build_summary(trending, new, pumpfun)
        assert "2 PumpFun graduations" in summary

    def test_build_summary_near_graduation(self):
        trending = []
        pumpfun = [{"graduated": False, "bonding_progress_pct": 85}]
        summary = scanner.DexScanner._build_summary(trending, [], pumpfun)
        assert "1 near-graduation" in summary

    def test_build_summary_empty(self):
        summary = scanner.DexScanner._build_summary([], [], [])
        assert summary == "No actionable signals detected"
