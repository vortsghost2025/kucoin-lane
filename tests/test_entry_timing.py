import pytest
from src.entry_timing import EntryTimingValidator


class TestEntryTimingValidator:
    def test_init_defaults(self):
        v = EntryTimingValidator()
        assert v.reversal_threshold_pct == 0.001
        assert v.baseline_prices == {}
        assert v.baseline_timestamps == {}
        assert v.price_history == {}

    def test_init_custom_threshold(self):
        v = EntryTimingValidator(reversal_threshold_pct=0.005)
        assert v.reversal_threshold_pct == 0.005

    def test_first_check_establishes_baseline(self):
        v = EntryTimingValidator()
        ok, reason = v.check_reversal_confirmation("SOL/USDT", 100.0)
        assert ok is False
        assert "First cycle check" in reason
        assert v.baseline_prices["SOL/USDT"] == 100.0

    def test_reversal_confirmed_when_price_above_threshold(self):
        v = EntryTimingValidator(reversal_threshold_pct=0.01)
        v.check_reversal_confirmation("SOL/USDT", 100.0)
        ok, reason = v.check_reversal_confirmation("SOL/USDT", 102.0)
        assert ok is True
        assert "Reversal confirmed" in reason

    def test_reversal_not_confirmed_below_threshold(self):
        v = EntryTimingValidator(reversal_threshold_pct=0.05)
        v.check_reversal_confirmation("SOL/USDT", 100.0)
        ok, reason = v.check_reversal_confirmation("SOL/USDT", 101.0)
        assert ok is False
        assert "Insufficient reversal" in reason

    def test_reversal_not_confirmed_when_declining(self):
        v = EntryTimingValidator(reversal_threshold_pct=0.01)
        v.check_reversal_confirmation("SOL/USDT", 100.0)
        ok, reason = v.check_reversal_confirmation("SOL/USDT", 99.0)
        assert ok is False
        assert "declining" in reason.lower() or "insufficient" in reason.lower()

    def test_price_history_capped_at_10(self):
        v = EntryTimingValidator()
        v.check_reversal_confirmation("SOL/USDT", 100.0)
        for i in range(15):
            v.check_reversal_confirmation("SOL/USDT", 100.0 + i)
        assert len(v.price_history["SOL/USDT"]) == 10

    def test_reset_baseline(self):
        v = EntryTimingValidator()
        v.check_reversal_confirmation("SOL/USDT", 100.0)
        v.reset_baseline("SOL/USDT")
        assert "SOL/USDT" not in v.baseline_prices
        assert v.price_history["SOL/USDT"] == []

    def test_get_baseline_age_seconds_none(self):
        v = EntryTimingValidator()
        assert v.get_baseline_age_seconds("SOL/USDT") is None

    def test_get_baseline_age_seconds_returns_float(self):
        v = EntryTimingValidator()
        v.check_reversal_confirmation("SOL/USDT", 100.0)
        age = v.get_baseline_age_seconds("SOL/USDT")
        assert isinstance(age, float)
        assert age >= 0

    def test_get_status_not_set(self):
        v = EntryTimingValidator()
        status = v.get_status("SOL/USDT")
        assert status["baseline_set"] is False
        assert status["status"] == "waiting_for_first_check"

    def test_get_status_set(self):
        v = EntryTimingValidator()
        v.check_reversal_confirmation("SOL/USDT", 100.0)
        status = v.get_status("SOL/USDT")
        assert status["baseline_set"] is True
        assert status["baseline_price"] == 100.0
        assert len(status["price_history"]) == 1
        assert "reversal_threshold" in status
