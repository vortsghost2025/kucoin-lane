"""
Portfolio-level circuit breaker to halt trading when drawdowns exceed limits.
Persist minimal state to survive restarts and enforce cooldown after a trip.
"""

import json
import logging
import os
import time
import datetime as dt
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitBreakTriggered(Exception):
    pass


class PortfolioCircuitBreaker:
    def __init__(
        self,
        starting_equity: float,
        max_drawdown_pct: float = 8.0,
        max_daily_loss_pct: float = 6.0,
        cooldown_minutes: int = 60,
        state_path: str = "portfolio_cb_state.json",
        requires_manual_reset: bool = True,
    ) -> None:
        self.starting_equity = max(starting_equity, 0)
        self.max_drawdown_pct = max_drawdown_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.cooldown_minutes = cooldown_minutes
        self.state_path = state_path
        self.requires_manual_reset = requires_manual_reset
        self.session_start_equity: float = self.starting_equity
        self.equity_peak: float = self.starting_equity
        self.last_equity: float = self.starting_equity
        self.tripped: bool = False
        self.trip_reason: str = ""
        self.trip_time: Optional[float] = None
        self._load_state()

    def _load_state(self) -> None:
        today = dt.date.today().isoformat()
        if not os.path.exists(self.state_path):
            self._persist(today)
            return
        try:
            with open(self.state_path, "r") as f:
                state = json.load(f)
        except Exception:
            logger.warning("Failed to load state from %s", self.state_path)
            self._persist(today)
            return
        
        # Defensive: ensure state is a dict
        if not isinstance(state, dict):
            logger.warning("Circuit breaker state is not a dict (type: %s), resetting", type(state).__name__)
            self._persist(today)
            return
        
        if state.get("date") != today:
            self._persist(today)
            return

        self.session_start_equity = float(
            state.get("session_start_equity", self.starting_equity)
        )
        self.equity_peak = float(state.get("equity_peak", self.starting_equity))
        self.last_equity = float(state.get("last_equity", self.starting_equity))
        self.tripped = bool(state.get("tripped", False))
        self.trip_reason = state.get("trip_reason", "")
        self.trip_time = state.get("trip_time")

    def _persist(self, date_str: str) -> None:
        state = {
            "date": date_str,
            "session_start_equity": self.session_start_equity,
            "equity_peak": self.equity_peak,
            "last_equity": self.last_equity,
            "tripped": self.tripped,
            "trip_reason": self.trip_reason,
            "trip_time": self.trip_time,
            "requires_manual_reset": self.requires_manual_reset,
        }
        try:
            with open(self.state_path, "w") as f:
                json.dump(state, f, indent=2)
        except Exception:
            logger.warning("Failed to persist state to %s", self.state_path)

    def check(self, current_equity: float) -> None:
        if self.tripped:
            if self.requires_manual_reset:
                raise CircuitBreakTriggered(
                    f"Portfolio CB TRIPPED (manual reset required): {self.trip_reason}"
                )
            if (
                self.trip_time
                and time.time() - self.trip_time > self.cooldown_minutes * 60
            ):
                self.tripped = False
                self.trip_reason = ""
                self.trip_time = None
            else:
                raise CircuitBreakTriggered(self.trip_reason)

        self.last_equity = current_equity
        self.equity_peak = max(self.equity_peak, current_equity)

        drawdown_pct = (
            ((self.equity_peak - current_equity) / self.equity_peak) * 100
            if self.equity_peak > 0
            else 0
        )
        if drawdown_pct >= self.max_drawdown_pct:
            self.tripped = True
            self.trip_reason = (
                f"Drawdown {drawdown_pct:.1f}% >= {self.max_drawdown_pct}%"
            )
            self.trip_time = time.time()
            self._persist(dt.date.today().isoformat())
            raise CircuitBreakTriggered(self.trip_reason)

        daily_loss = self.session_start_equity - current_equity
        daily_loss_pct = (
            (daily_loss / self.session_start_equity) * 100
            if self.session_start_equity > 0
            else 0
        )
        if daily_loss_pct >= self.max_daily_loss_pct:
            self.tripped = True
            self.trip_reason = (
                f"Daily loss {daily_loss_pct:.1f}% >= {self.max_daily_loss_pct}%"
            )
            self.trip_time = time.time()
            self._persist(dt.date.today().isoformat())
            raise CircuitBreakTriggered(self.trip_reason)

        self._persist(dt.date.today().isoformat())

    def is_triggered(self) -> bool:
        return self.tripped

    def reset(self) -> None:
        self.tripped = False
        self.trip_reason = ""
        self.trip_time = None
        self._persist(dt.date.today().isoformat())
