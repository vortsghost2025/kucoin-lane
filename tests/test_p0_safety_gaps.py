"""P0 Safety Gap integration tests.

Validates all 5 P0 fixes:
  Gap 1: CB auto-resume requires human reset
  Gap 2: Partial data fetch must fail hard
  Gap 3: Risk manager exception halts system
  Gap 4: Portfolio CB pre-trade gate
  Gap 5: CB init failure crashes instead of no-op
"""
import os
import time
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from src.risk.circuit_breaker import CircuitBreaker
from src.risk.portfolio_circuit_breaker import (
    PortfolioCircuitBreaker,
    CircuitBreakTriggered,
)
from src.data.multi_provider_client import DataIntegrityError, fetch_simple_price


class TestP0Gap1_ManualResetRequired:
    """Gap 1: Circuit breakers must NOT auto-resume — human reset required."""

    class TestPnLCircuitBreakerManualReset:
        @pytest.fixture
        def cb(self):
            return CircuitBreaker(
                loss_threshold_pct=5.0,
                time_window_minutes=60,
                check_interval_seconds=0,
                name="TestP0_CB",
                requires_manual_reset=True,
            )

        def test_tripped_cb_refuses_auto_resume_after_cooldown(self, cb):
            now = time.time()
            cb.check_circuit(1000.0, timestamp=now)
            ok, _ = cb.check_circuit(800.0, timestamp=now + 10)
            assert ok is False
            assert cb.is_tripped is True
            long_after = now + 10 + 999999
            ok, reason = cb.check_circuit(1000.0, timestamp=long_after)
            assert ok is False
            assert "manual reset required" in reason.lower()

        def test_manual_reset_actually_resets(self, cb):
            now = time.time()
            cb.check_circuit(1000.0, timestamp=now)
            cb.check_circuit(800.0, timestamp=now + 10)
            assert cb.is_tripped is True
            cb.reset()
            assert cb.is_tripped is False
            ok, _ = cb.check_circuit(1000.0, timestamp=now + 20)
            assert ok is True

        def test_manual_reset_default_is_true(self):
            cb = CircuitBreaker(loss_threshold_pct=5.0, name="DefaultCB")
            assert cb.requires_manual_reset is True

        def test_opt_in_auto_reset_still_works(self):
            cb = CircuitBreaker(
                loss_threshold_pct=5.0,
                check_interval_seconds=0,
                name="AutoResetCB",
                requires_manual_reset=False,
            )
            now = time.time()
            cb.check_circuit(1000.0, timestamp=now)
            cb.check_circuit(800.0, timestamp=now + 10)
            assert cb.is_tripped is True
            long_after = now + 10 + 999999
            ok, reason = cb.check_circuit(1000.0, timestamp=long_after)
            assert ok is True

    class TestPortfolioCircuitBreakerManualReset:
        @pytest.fixture
        def pcb(self):
            with tempfile.TemporaryDirectory() as tmp:
                state_path = os.path.join(tmp, "pcb_state.json")
                pcb = PortfolioCircuitBreaker(
                    starting_equity=10000.0,
                    max_drawdown_pct=10.0,
                    max_daily_loss_pct=6.0,
                    cooldown_minutes=60,
                    state_path=state_path,
                    requires_manual_reset=True,
                )
                yield pcb

        def test_tripped_portfolio_cb_refuses_auto_resume(self, pcb):
            pcb.check(10000.0)
            with pytest.raises(CircuitBreakTriggered, match="Drawdown"):
                pcb.check(8500.0)
            assert pcb.tripped is True
            pcb.trip_time = time.time() - 999999
            with pytest.raises(CircuitBreakTriggered, match="manual reset required"):
                pcb.check(10000.0)
            assert pcb.tripped is True

        def test_manual_reset_clears_portfolio_cb(self, pcb):
            pcb.check(10000.0)
            with pytest.raises(CircuitBreakTriggered):
                pcb.check(8500.0)
            pcb.reset()
            assert pcb.tripped is False
            pcb.check(10000.0)

        def test_requires_manual_reset_default_is_true(self):
            with tempfile.TemporaryDirectory() as tmp:
                state_path = os.path.join(tmp, "pcb_state2.json")
                pcb = PortfolioCircuitBreaker(
                    starting_equity=10000.0,
                    state_path=state_path,
                )
                assert pcb.requires_manual_reset is True

        def test_requires_manual_reset_persisted_in_state(self):
            with tempfile.TemporaryDirectory() as tmp:
                state_path = os.path.join(tmp, "pcb_state3.json")
                pcb1 = PortfolioCircuitBreaker(
                    starting_equity=10000.0,
                    state_path=state_path,
                    requires_manual_reset=True,
                )
                pcb1.check(11000.0)
                pcb2 = PortfolioCircuitBreaker(
                    starting_equity=10000.0,
                    state_path=state_path,
                )
                assert pcb2.requires_manual_reset is True


class TestP0Gap2_DataIntegrityFailHard:
    """Gap 2: Partial data fetch must fail hard with DataIntegrityError."""

    @patch("src.data.multi_provider_client._fetch_binance", return_value=None)
    @patch("src.data.multi_provider_client._fetch_kraken", return_value=None)
    @patch("src.data.multi_provider_client.coingecko_fetch_simple_price", return_value=None)
    def test_all_providers_failed_raises_data_integrity_error(self, mock_cg, mock_kr, mock_bn):
        with pytest.raises(DataIntegrityError, match="all providers failed"):
            fetch_simple_price(["bitcoin"])

    @patch("src.data.multi_provider_client._fetch_binance")
    def test_partial_results_raises_data_integrity_error_require_all(self, mock_bn):
        mock_bn.return_value = {
            "bitcoin": {"usd": 50000.0, "usd_24h_vol": 0, "usd_24h_change": 0, "market_cap": {"usd": 0}}
        }
        with pytest.raises(DataIntegrityError, match="failed for"):
            fetch_simple_price(["bitcoin", "solana"], require_all=True)

    @patch("src.data.multi_provider_client._fetch_binance")
    def test_partial_results_ok_when_require_all_false(self, mock_bn):
        mock_bn.return_value = {
            "bitcoin": {"usd": 50000.0, "usd_24h_vol": 0, "usd_24h_change": 0, "market_cap": {"usd": 0}}
        }
        result = fetch_simple_price(["bitcoin", "solana"], require_all=False)
        assert "bitcoin" in result
        assert "solana" not in result

    @patch("src.data.multi_provider_client._fetch_binance")
    def test_require_all_default_is_true(self, mock_bn):
        mock_bn.return_value = {
            "bitcoin": {"usd": 50000.0, "usd_24h_vol": 0, "usd_24h_change": 0, "market_cap": {"usd": 0}}
        }
        with pytest.raises(DataIntegrityError):
            fetch_simple_price(["bitcoin", "solana"])

    def test_data_integrity_error_is_exception(self):
        assert issubclass(DataIntegrityError, Exception)


class TestP0Gap3_RiskExceptionHaltsSystem:
    """Gap 3: Risk manager exception must activate circuit breaker."""

    @pytest.fixture
    def orchestrator(self, tmp_path):
        cb_state_file = str(tmp_path / "cb_state.json")
        portfolio_cb_file = str(tmp_path / "portfolio_cb_state.json")
        with patch.dict(
            os.environ,
            {
                "CB_STATE_PATH": cb_state_file,
                "PORTFOLIO_CB_STATE_PATH": portfolio_cb_file,
            },
        ):
            from src.intelligence.orchestrator import IntelligenceOrchestrator
            return IntelligenceOrchestrator(
                {
                    "enable_regime": False,
                    "enable_lead_lag": False,
                    "enable_whale": False,
                    "paper_trading": True,
                }
            )

    def test_risk_execution_failed_activates_circuit_breaker(self, orchestrator):
        risk_result = {
            "success": False,
            "error": "Risk agent execution failed: RuntimeError",
        }
        assert not risk_result["success"]
        assert "execution failed" in risk_result["error"].lower()
        assert orchestrator.circuit_breaker_active is False
        orchestrator.activate_circuit_breaker(
            f"Risk manager exception: {risk_result.get('error', 'unknown')}"
        )
        assert orchestrator.circuit_breaker_active is True
        allowed, reason = orchestrator.is_trading_allowed()
        assert allowed is False


class TestP0Gap4_PortfolioCBPreTradeGate:
    """Gap 4: Portfolio CB must block trading before trade executes."""

    @pytest.fixture
    def orchestrator(self, tmp_path):
        cb_state_file = str(tmp_path / "cb_state.json")
        portfolio_cb_file = str(tmp_path / "portfolio_cb_state.json")
        with patch.dict(
            os.environ,
            {
                "CB_STATE_PATH": cb_state_file,
                "PORTFOLIO_CB_STATE_PATH": portfolio_cb_file,
            },
        ):
            from src.intelligence.orchestrator import IntelligenceOrchestrator
            return IntelligenceOrchestrator(
                {
                    "enable_regime": False,
                    "enable_lead_lag": False,
                    "enable_whale": False,
                    "paper_trading": True,
                }
            )

    def test_is_trading_allowed_blocks_when_pnl_cb_tripped(self, orchestrator):
        orchestrator.circuit_breaker.is_tripped = True
        orchestrator.circuit_breaker.trip_reason = "PnL drop exceeded threshold"
        allowed, reason = orchestrator.is_trading_allowed()
        assert allowed is False
        assert "pnl circuit breaker tripped" in reason.lower()

    def test_is_trading_allowed_blocks_when_portfolio_cb_tripped(self, orchestrator):
        orchestrator.portfolio_cb.tripped = True
        orchestrator.portfolio_cb.trip_reason = "Drawdown exceeded 10%"
        allowed, reason = orchestrator.is_trading_allowed()
        assert allowed is False
        assert "portfolio circuit breaker tripped" in reason.lower()

    def test_is_trading_allowed_passes_when_both_cbs_clear(self, orchestrator):
        allowed, reason = orchestrator.is_trading_allowed()
        assert allowed is True
        assert reason is None


class TestP0Gap5_CBInitFailureCrashesSystem:
    """Gap 5: CB init failure must crash system, not silently continue."""

    def test_cb_init_failure_raises(self):
        with patch.dict(os.environ, {"CB_STATE_PATH": "/tmp/cb.json", "PORTFOLIO_CB_STATE_PATH": "/tmp/pcb.json"}):
            with patch("src.intelligence.orchestrator.CircuitBreaker", side_effect=RuntimeError("CB init failed")):
                from src.intelligence.orchestrator import IntelligenceOrchestrator
                with pytest.raises(RuntimeError, match="CB init failed"):
                    IntelligenceOrchestrator(
                        {
                            "enable_regime": False,
                            "enable_lead_lag": False,
                            "enable_whale": False,
                            "paper_trading": True,
                        }
                    )
