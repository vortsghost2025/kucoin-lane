import pytest
import time
from datetime import datetime, timezone, timedelta
from src.execution.trailing_stop import (
    TrailingStopManager,
    ProgressiveROI,
    CustomStopLoss,
    DEFAULT_ROI_TABLE,
)


class TestTrailingStopManager:
    @pytest.fixture
    def mgr(self):
        return TrailingStopManager({
            "trail_pct": 1.5,
            "activation_pct": 2.0,
            "step_pct": 0.5,
        })

    @pytest.fixture
    def default_mgr(self):
        return TrailingStopManager()

    def test_defaults(self, default_mgr):
        assert default_mgr.trail_pct == 1.5
        assert default_mgr.activation_pct == 2.0
        assert default_mgr.step_pct == 0.5

    def test_no_trail_before_activation(self, mgr):
        result = mgr.update(
            trade_id=1,
            entry_price=100.0,
            current_price=101.0,
            original_sl=98.0,
            direction="long",
        )
        assert result["trailing_active"] is False
        assert result["stop_loss"] == 98.0

    def test_trail_activates_after_threshold(self, mgr):
        result = mgr.update(
            trade_id=1,
            entry_price=100.0,
            current_price=102.5,
            original_sl=98.0,
            direction="long",
        )
        assert result["trailing_active"] is True
        assert result["stop_loss"] > 98.0

    def test_trail_ratchets_up(self, mgr):
        mgr.update(1, 100.0, 102.5, 98.0, "long")
        r1 = mgr.update(1, 100.0, 103.0, 98.0, "long")
        r2 = mgr.update(1, 100.0, 105.0, 98.0, "long")
        assert r2["stop_loss"] > r1["stop_loss"]
        assert r2["high_water"] == 105.0

    def test_trail_never_goes_below_original_sl(self, mgr):
        result = mgr.update(
            trade_id=2,
            entry_price=100.0,
            current_price=102.0,
            original_sl=98.0,
            direction="long",
        )
        assert result["stop_loss"] >= 98.0

    def test_remove_clears_state(self, mgr):
        mgr.update(1, 100.0, 105.0, 98.0, "long")
        mgr.remove(1)
        result = mgr.update(1, 100.0, 105.0, 98.0, "long")
        assert result["high_water"] == 105.0

    def test_psar_overrides_pct_trail(self, mgr):
        result = mgr.update(
            trade_id=3,
            entry_price=100.0,
            current_price=102.5,
            original_sl=98.0,
            direction="long",
            psar_value=100.5,
        )
        assert result["trailing_active"] is True
        assert result["stop_loss"] == 100.5

    def test_psar_below_original_sl_ignored(self, mgr):
        result = mgr.update(
            trade_id=4,
            entry_price=100.0,
            current_price=102.5,
            original_sl=98.0,
            direction="long",
            psar_value=95.0,
        )
        assert result["stop_loss"] >= 98.0

    def test_short_trailing(self, mgr):
        result = mgr.update(
            trade_id=5,
            entry_price=100.0,
            current_price=97.5,
            original_sl=102.0,
            direction="short",
        )
        assert result["trailing_active"] is True
        assert result["stop_loss"] < 102.0


class TestParabolicSAR:
    def test_insufficient_data(self):
        result = TrailingStopManager.calculate_psar([100], [99], [100])
        assert result == [None]

    def test_uptrend_sar_below_price(self):
        closes = [100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120]
        highs = [c + 1 for c in closes]
        lows = [c - 1 for c in closes]
        sar = TrailingStopManager.calculate_psar(highs, lows, closes)
        assert len(sar) == len(closes)
        assert sar[0] is None
        for i in range(2, len(sar)):
            if sar[i] is not None:
                assert sar[i] < closes[i]

    def test_downtrend_sar_above_price(self):
        closes = [120, 118, 116, 114, 112, 110, 108, 106, 104, 102, 100]
        highs = [c + 1 for c in closes]
        lows = [c - 1 for c in closes]
        sar = TrailingStopManager.calculate_psar(highs, lows, closes)
        assert len(sar) == len(closes)
        for i in range(3, len(sar)):
            if sar[i] is not None and closes[i] < closes[i - 1]:
                assert sar[i] > closes[i]

    def test_flat_market(self):
        closes = [100.0] * 20
        highs = [100.5] * 20
        lows = [99.5] * 20
        sar = TrailingStopManager.calculate_psar(highs, lows, closes)
        assert len(sar) == 20


class TestProgressiveROI:
    @pytest.fixture
    def roi(self):
        return ProgressiveROI()

    @pytest.fixture
    def custom_roi(self):
        return ProgressiveROI({
            "roi_table": {0: 3.0, 30: 1.0, 60: 0.5, 120: 0.35},
        })

    def test_default_table(self, roi):
        assert roi.roi_table == DEFAULT_ROI_TABLE

    def test_get_target_at_entry(self, roi):
        assert roi.get_target_pct(0) == 6.0

    def test_get_target_at_30_min(self, roi):
        assert roi.get_target_pct(30) == 4.0

    def test_get_target_at_240_min(self, roi):
        assert roi.get_target_pct(240) == 1.0

    def test_get_target_between_steps(self, roi):
        # 45 min: between 30→4.0% and 60→3.0%, should use 4.0%
        assert roi.get_target_pct(45) == 4.0

    def test_custom_table(self, custom_roi):
        assert custom_roi.get_target_pct(0) == 3.0
        assert custom_roi.get_target_pct(120) == 0.35

    def test_check_no_exit_insufficient_profit(self, roi):
        # Entry was 5 seconds ago — need 5% profit, won't have it
        entry_time = datetime.now(timezone.utc).isoformat()
        should_exit, _, _, _ = roi.check(entry_time, 101.0, 100.0)
        assert should_exit is False

    def test_check_exit_after_long_hold(self, roi):
        # Entry 5 hours ago — need 1.0%, price is +1.5%
        entry_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        should_exit, current_pct, target_pct, minutes = roi.check(
            entry_time, 101.5, 100.0
        )
        assert should_exit is True
        assert current_pct == pytest.approx(1.5, abs=0.01)
        assert target_pct == 1.0
        assert minutes >= 240

    def test_check_invalid_entry_time(self, roi):
        should_exit, _, _, _ = roi.check("not-a-date", 101.0, 100.0)
        assert should_exit is False

    def test_check_zero_entry_price(self, roi):
        entry_time = datetime.now(timezone.utc).isoformat()
        should_exit, _, _, _ = roi.check(entry_time, 101.0, 0.0)
        assert should_exit is False


class TestCustomStopLoss:
    @pytest.fixture
    def csl(self):
        return CustomStopLoss({"breakeven_activation_pct": 1.0})

    @pytest.fixture
    def default_csl(self):
        return CustomStopLoss()

    def test_defaults(self, default_csl):
        assert default_csl.breakeven_activation_pct == 1.0

    def test_no_breakeven_below_threshold(self, csl):
        result = csl.check(entry_price=100.0, current_price=100.5, original_sl=98.0)
        assert result["breakeven_active"] is False
        assert result["stop_loss"] == 98.0

    def test_breakeven_activates(self, csl):
        result = csl.check(entry_price=100.0, current_price=101.1, original_sl=98.0)
        assert result["breakeven_active"] is True
        assert result["stop_loss"] == 100.0

    def test_breakeven_never_lowers_sl(self, csl):
        # If original SL is already above entry, don't lower it
        result = csl.check(entry_price=100.0, current_price=101.0, original_sl=100.5)
        assert result["stop_loss"] == 100.5

    def test_unrealized_pct(self, csl):
        result = csl.check(entry_price=100.0, current_price=101.0, original_sl=98.0)
        assert result["unrealized_pct"] == pytest.approx(1.0, abs=0.01)

    def test_short_breakeven(self, csl):
        result = csl.check(
            entry_price=100.0, current_price=98.8, original_sl=102.0, direction="short"
        )
        assert result["breakeven_active"] is True
        assert result["stop_loss"] == 100.0

    def test_zero_entry_price(self, csl):
        result = csl.check(entry_price=0.0, current_price=100.0, original_sl=98.0)
        assert result["breakeven_active"] is False
        assert result["stop_loss"] == 98.0
