import pytest
from unittest.mock import patch, MagicMock
from src.data.dex_intelligence_agent import DexIntelligenceAgent


class TestDexIntelligenceAgent:
    def test_init_default_config(self):
        agent = DexIntelligenceAgent()
        assert agent.scanner is not None
        assert agent._scan_interval == 300
        assert agent._min_composite_score == 0.3
        assert agent._latest_signals == {}

    def test_init_with_config(self):
        config = {
            "chains": ["solana", "base"],
            "rpc_url": "https://api.mainnet-beta.solana.com",
            "scan_interval_seconds": 60,
            "min_composite_score": 0.5,
        }
        agent = DexIntelligenceAgent(config)
        assert agent._scan_interval == 60
        assert agent._min_composite_score == 0.5

    def test_init_with_rpc_env(self, monkeypatch):
        monkeypatch.setenv("DEX_PUMPFUN_RPC_URL", "https://test-rpc.example.com")
        agent = DexIntelligenceAgent(config={"chains": ["solana"]})
        assert agent.scanner.pf is not None

    @patch("src.data.dex_intelligence_agent.DexScanner")
    def test_execute_success(self, mock_scanner_class):
        mock_scanner = MagicMock()
        mock_scanner.full_scan.return_value = {
            "scan_time": "2026-06-05T10:00:00Z",
            "chain": "solana",
            "summary": "2 STRONG_BUY signals; 1 BUY signal",
            "top_trending": [
                {"pair": "STRONG/USDT", "signal": "STRONG_BUY", "composite_score": 0.7, "chain": "solana"},
                {"pair": "WEAK/USDT", "signal": "AVOID", "composite_score": 0.1, "chain": "solana"},
            ],
            "top_new_pools": [
                {"pair": "NEW/SOL", "signal": "BUY", "composite_score": 0.45, "chain": "solana"},
            ],
            "pumpfun_graduation_candidates": [],
        }
        mock_scanner_class.return_value = mock_scanner
        agent = DexIntelligenceAgent(config={"chains": ["solana"]})
        result = agent.execute({"chain": "solana"})
        assert result["success"] is True
        assert result["action"] == "dex_intelligence"
        assert len(result["data"]["dex_signals"]) == 2
        assert "STRONG_BUY" in result["data"]["scan_summary"]
        assert result["data"]["chain"] == "solana"
        assert result["data"]["total_scanned"] == 3
        assert result["data"]["actionable_count"] == 2

    @patch("src.data.dex_intelligence_agent.DexScanner")
    def test_execute_filters_below_min_score(self, mock_scanner_class):
        mock_scanner = MagicMock()
        mock_scanner.full_scan.return_value = {
            "scan_time": "2026-06-05T10:00:00Z",
            "chain": "solana",
            "summary": "No actionable signals detected",
            "top_trending": [
                {"pair": "LOW/USDT", "signal": "BUY", "composite_score": 0.35, "chain": "solana"},
            ],
            "top_new_pools": [],
            "pumpfun_graduation_candidates": [],
        }
        mock_scanner_class.return_value = mock_scanner
        agent = DexIntelligenceAgent(config={"min_composite_score": 0.5})
        result = agent.execute({"chain": "solana"})
        assert result["success"] is True
        assert result["data"]["actionable_count"] == 0
        assert result["data"]["dex_signals"] == []

    @patch("src.data.dex_intelligence_agent.DexScanner")
    def test_execute_uses_input_min_score_override(self, mock_scanner_class):
        mock_scanner = MagicMock()
        mock_scanner.full_scan.return_value = {
            "scan_time": "2026-06-05T10:00:00Z",
            "chain": "solana",
            "summary": "1 BUY signal",
            "top_trending": [
                {"pair": "MID/USDT", "signal": "BUY", "composite_score": 0.45, "chain": "solana"},
            ],
            "top_new_pools": [],
            "pumpfun_graduation_candidates": [],
        }
        mock_scanner_class.return_value = mock_scanner
        agent = DexIntelligenceAgent(config={"min_composite_score": 0.5})
        result = agent.execute({"chain": "solana", "min_composite_score": 0.4})
        assert result["data"]["actionable_count"] == 1

    @patch("src.data.dex_intelligence_agent.DexScanner")
    def test_execute_handles_exception(self, mock_scanner_class):
        mock_scanner = MagicMock()
        mock_scanner.full_scan.side_effect = Exception("DEX API down")
        mock_scanner_class.return_value = mock_scanner
        agent = DexIntelligenceAgent()
        result = agent.execute({"chain": "solana"})
        assert result["success"] is False
        assert "DEX scan failed" in result["error"]
        assert result["data"]["dex_signals"] == []

    def test_get_latest_signals_empty_initially(self):
        agent = DexIntelligenceAgent()
        assert agent.get_latest_signals() == {}

    @patch("src.data.dex_intelligence_agent.DexScanner")
    def test_get_latest_signals_after_execute(self, mock_scanner_class):
        mock_scanner = MagicMock()
        mock_scanner.full_scan.return_value = {
            "scan_time": "2026-06-05T10:00:00Z",
            "chain": "solana",
            "summary": "1 STRONG_BUY signal",
            "top_trending": [
                {"pair": "X/USDT", "signal": "STRONG_BUY", "composite_score": 0.7, "chain": "solana"},
            ],
            "top_new_pools": [],
            "pumpfun_graduation_candidates": [],
        }
        mock_scanner_class.return_value = mock_scanner
        agent = DexIntelligenceAgent()
        agent.execute({"chain": "solana"})
        latest = agent.get_latest_signals()
        assert latest["chain"] == "solana"
        assert latest["scan_summary"] == "1 STRONG_BUY signal"
        assert len(latest["dex_signals"]) == 1

    @patch("src.data.dex_intelligence_agent.DexScanner")
    def test_get_status_report_includes_dex_fields(self, mock_scanner_class):
        mock_scanner = MagicMock()
        mock_scanner_class.return_value = mock_scanner
        agent = DexIntelligenceAgent()
        report = agent.get_status_report()
        assert "latest_scan_time" in report
        assert "latest_signal_count" in report
        assert report["latest_signal_count"] == 0
        assert report["name"] == "DexIntelligenceAgent"
