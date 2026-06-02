import pytest
from src.intelligence.market_analyzer import MarketAnalysisAgent, MarketRegime


class TestMarketAnalysisAgent:
    @pytest.fixture
    def config(self):
        return {
            "rsi_period": 14,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
            "downtrend_threshold": -5,
        }

    @pytest.fixture
    def agent(self, config):
        return MarketAnalysisAgent(config)

    def test_init(self, agent):
        assert agent.agent_name == "MarketAnalysisAgent"
        assert agent.rsi_period == 14

    def test_execute_no_data(self, agent):
        result = agent.execute({"market_data": {}})
        assert result["success"] is False

    def test_execute_valid_data(self, agent):
        result = agent.execute({
            "market_data": {
                "SOL/USDT": {
                    "current_price": 100.0,
                    "price_change_24h_pct": 5.0,
                    "volume_24h": 1000000.0,
                }
            }
        })
        assert result["success"] is True
        data = result["data"]
        assert "analysis" in data
        assert "regime" in data
        assert "downtrend_detected" in data

    def test_calculate_rsi_simple(self, agent):
        assert agent._calculate_rsi_simple(0) == 50
        assert agent._calculate_rsi_simple(100) == 60
        assert agent._calculate_rsi_simple(-100) == 40
        assert 0 <= agent._calculate_rsi_simple(1000) <= 100
        assert 0 <= agent._calculate_rsi_simple(-1000) <= 100

    def test_calculate_rsi_welder_insufficient_data(self, agent):
        assert agent.calculate_rsi([100.0], 14) is None
        assert agent.calculate_rsi([], 14) is None
        assert agent.calculate_rsi([100.0] * 5, 14) is None

    def test_calculate_rsi_welder_all_gains(self, agent):
        closes = [100.0 + i for i in range(20)]
        rsi = agent.calculate_rsi(closes, 14)
        assert rsi is not None
        assert rsi == 100.0

    def test_calculate_rsi_welder_all_losses(self, agent):
        closes = [100.0 - i for i in range(20)]
        rsi = agent.calculate_rsi(closes, 14)
        assert rsi is not None
        assert rsi == 0.0

    def test_calculate_rsi_welder_mixed(self, agent):
        closes = [100.0, 101.0, 99.0, 102.0, 98.0, 103.0, 97.0,
                  104.0, 96.0, 105.0, 95.0, 106.0, 94.0, 107.0,
                  93.0, 108.0, 92.0, 109.0, 91.0, 110.0]
        rsi = agent.calculate_rsi(closes, 14)
        assert rsi is not None
        assert 0 < rsi < 100

    def test_calculate_rsi_welder_flat(self, agent):
        closes = [100.0] * 20
        rsi = agent.calculate_rsi(closes, 14)
        assert rsi is not None
        assert rsi == 50.0

    def test_calculate_rsi_with_closes_data(self, agent):
        data = {
            "current_price": 100.0,
            "price_change_24h_pct": 5.0,
            "volume_24h": 1000000.0,
            "closes": [100.0 + i for i in range(20)],
        }
        rsi = agent._calculate_rsi(data)
        assert rsi == 100.0

    def test_calculate_rsi_fallback_no_closes(self, agent):
        data = {
            "current_price": 100.0,
            "price_change_24h_pct": 5.0,
            "volume_24h": 1000000.0,
        }
        rsi = agent._calculate_rsi(data)
        assert rsi == 50.5

    def test_calculate_macd_simple(self, agent):
        assert agent._calculate_macd_simple(5.0) == 10.0
        assert agent._calculate_macd_simple(-3.0) == -6.0

    def test_determine_trend(self, agent):
        assert agent._determine_trend(3.0, 50) == "uptrend"
        assert agent._determine_trend(-3.0, 50) == "downtrend"
        assert agent._determine_trend(0, 50) == "sideways"

    def test_classify_volatility(self, agent):
        assert agent._classify_volatility(15) == "high"
        assert agent._classify_volatility(7) == "medium"
        assert agent._classify_volatility(2) == "low"

    def test_classify_regime(self, agent):
        assert agent._classify_regime(-10, 20, "low") == MarketRegime.BEARISH.value
        assert agent._classify_regime(5, 56, "low") == MarketRegime.BULLISH.value
        assert agent._classify_regime(0, 50, "low") == MarketRegime.SIDEWAYS.value

    def test_generate_signal(self, agent):
        s = agent._generate_signal(0, 50, "SOL/USDT")
        assert 0 <= s <= 100
        assert s == pytest.approx(50, abs=1)

    def test_generate_signal_momentum(self, agent):
        s = agent._generate_signal(10, 70, "SOL/USDT")
        assert s > 60

    def test_determine_overall_regime_bearish_wins(self, agent):
        analysis = {
            "SOL": {"regime": "bearish"},
            "BTC": {"regime": "bullish"},
        }
        assert agent._determine_overall_regime(analysis) == "bearish"

    def test_determine_overall_regime_empty(self, agent):
        assert agent._determine_overall_regime({}) == "unknown"

    def test_calculate_overall_confidence(self, agent):
        analysis = {
            "SOL": {"signal_strength": 0.8},
            "BTC": {"signal_strength": 0.6},
        }
        assert agent._calculate_overall_confidence(analysis) == 0.7

    def test_calculate_overall_confidence_empty(self, agent):
        assert agent._calculate_overall_confidence({}) == 0.0

    def test_entry_timing_integration(self, config):
        config["entry_timing_config"] = {"enabled": True, "reversal_threshold_pct": 0.001}
        agent = MarketAnalysisAgent(config)
        assert agent.entry_timing_enabled is True
        assert agent.entry_timing_validator is not None
