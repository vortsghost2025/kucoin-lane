"""
Circuit Breaker - Pause trading if losses exceed threshold
Prevents catastrophic drawdown by implementing automatic circuit breaker logic
"""

import time
import logging
from typing import Optional, Tuple
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    Monitors PnL and pauses trading if losses exceed threshold.
    If PnL drops X% in Y minutes, trading is paused but positions NOT closed.
    """

    def __init__(
        self,
        loss_threshold_pct: float = 8.0,
        time_window_minutes: int = 60,
        check_interval_seconds: int = 300,
        name: str = "CircuitBreaker",
    ):
        self.loss_threshold_pct = loss_threshold_pct
        self.time_window_minutes = time_window_minutes
        self.check_interval_seconds = check_interval_seconds
        self.name = name

        self.pnl_history = deque()
        self.last_check_time = 0
        self.is_tripped = False
        self.trip_time: Optional[float] = None
        self.trip_reason = ""

    def record_pnl(self, pnl_usd: float, timestamp: Optional[float] = None) -> None:
        timestamp = timestamp or time.time()
        self.pnl_history.append((timestamp, pnl_usd))

        cutoff_time = timestamp - (self.time_window_minutes * 60)
        while self.pnl_history and self.pnl_history[0][0] < cutoff_time:
            self.pnl_history.popleft()

    def check_circuit(
        self, current_pnl_usd: float, timestamp: Optional[float] = None
    ) -> Tuple[bool, str]:
        timestamp = timestamp or time.time()
        self.record_pnl(current_pnl_usd, timestamp)

        if timestamp - self.last_check_time < self.check_interval_seconds:
            return not self.is_tripped, ""

        self.last_check_time = timestamp

        if len(self.pnl_history) < 2:
            return True, "Insufficient data for circuit check"

        if self.is_tripped:
            time_since_trip = timestamp - (self.trip_time or timestamp)
            cooldown = self.time_window_minutes * 60 * 2
            if time_since_trip < cooldown:
                return (
                    False,
                    f"Circuit breaker cooldown ({time_since_trip:.0f}/{cooldown:.0f}s)",
                )

            self.is_tripped = False
            self.trip_time = None
            self.trip_reason = ""
            logger.info(f"[{self.name}] Circuit breaker reset after cooldown")
            return True, "Circuit breaker reset after cooldown"

        oldest_pnl = self.pnl_history[0][1]
        pnl_drop = oldest_pnl - current_pnl_usd
        pnl_drop_pct = (pnl_drop / abs(oldest_pnl)) * 100 if oldest_pnl != 0 else 0

        if pnl_drop_pct >= self.loss_threshold_pct:
            self.is_tripped = True
            self.trip_time = timestamp
            self.trip_reason = (
                f"PnL dropped {pnl_drop_pct:.1f}% in {self.time_window_minutes}min"
            )
            logger.critical(
                f"[{self.name}] CIRCUIT BREAKER TRIPPED: {self.trip_reason}"
            )
            return False, self.trip_reason

        return True, f"Healthy (PnL drop: {pnl_drop_pct:.1f}%)"

    def is_triggered(self) -> bool:
        return self.is_tripped

    def reset(self) -> None:
        self.pnl_history.clear()
        self.is_tripped = False
        self.trip_time = None
        self.trip_reason = ""
        self.last_check_time = 0
