import time
import pytest
from src.intelligence.lead_lag import LeadLagMonitor


class TestLeadLagMonitor:
    @pytest.fixture
    def monitor(self):
        return LeadLagMonitor(
            rapid_move_threshold=0.005,
            rapid_move_window=30,
            volume_spike_multiplier=3.0,
        )

    def test_init(self, monitor):
        assert monitor.threshold == 0.005
        assert monitor.window == 30
        assert monitor.volume_multiplier == 3.0
        assert monitor.current_signal == "NORMAL"
        assert len(monitor.price_history) == 0

    def test_detect_cascade_insufficient_data(self, monitor):
        assert monitor._detect_cascade() == "NORMAL"

    def test_detect_cascade_normal(self, monitor):
        now = time.time()
        for i in range(10):
            monitor.price_history.append((now - 10 + i, 100.0))
            monitor.volume_history.append((now - 10 + i, 100.0))
        result = monitor._detect_cascade()
        assert result == "NORMAL"

    def test_detect_cascade_warning(self, monitor):
        now = time.time()
        recent_t = now - 18
        for i in range(10):
            t = recent_t + i * 2
            price = 100.0 - i * 0.6
            monitor.price_history.append((t, price))
            monitor.volume_history.append((t, 100.0))
        assert monitor._detect_cascade() == "WARNING"

    def test_detect_cascade_danger_with_volume_spike(self, monitor):
        now = time.time()
        for i in range(90):
            monitor.price_history.append((now - 200 + i, 100.0))
            monitor.volume_history.append((now - 200 + i, 1.0))
        recent_t = now - 18
        for i in range(10):
            t = recent_t + i * 2
            price = 100.0 - i * 0.6
            monitor.price_history.append((t, price))
            monitor.volume_history.append((t, 10.0))
        result = monitor._detect_cascade()
        assert result == "DANGER"

    def test_detect_cascade_warning_no_volume(self, monitor):
        now = time.time()
        recent_t = now - 18
        for i in range(10):
            t = recent_t + i * 2
            price = 100.0 - i * 0.6
            monitor.price_history.append((t, price))
            monitor.volume_history.append((t, 100.0))
        result = monitor._detect_cascade()
        assert result == "WARNING"

    def test_detect_cascade_opportunity(self, monitor):
        now = time.time()
        for i in range(90):
            monitor.price_history.append((now - 200 + i, 100.0))
            monitor.volume_history.append((now - 200 + i, 1.0))
        recent_t = now - 18
        for i in range(10):
            t = recent_t + i * 2
            price = 100.0 + i * 0.6
            monitor.price_history.append((t, price))
            monitor.volume_history.append((t, 10.0))
        result = monitor._detect_cascade()
        assert result == "OPPORTUNITY"

    def test_get_status(self, monitor):
        status = monitor.get_status()
        assert status["connected"] == monitor.running
        assert status["signal"] == "NORMAL"
        assert "current_price" in status

    def test_stop(self, monitor):
        monitor.running = True
        monitor.stop()
        assert monitor.running is False

    def test_signal_persistence_across_trades(self, monitor):
        now = time.time()
        for i in range(10):
            monitor.price_history.append((now, 100.0))
            monitor.volume_history.append((now, 100.0))
        assert monitor.current_signal == "NORMAL"

    def test_detect_cascade_edge_empty_window(self, monitor):
        now = time.time()
        for i in range(3):
            monitor.price_history.append((now - 100, 100.0))
            monitor.volume_history.append((now - 100, 100.0))
        assert monitor._detect_cascade() == "NORMAL"
