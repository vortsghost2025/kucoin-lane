"""Trailing Stop Manager — PSAR-inspired trailing stop for open positions.

At $110 capital with 2% stop-loss, a static SL leaves money on the table
when price runs favorably. This module ratchets the stop-loss upward
(never downward for longs) as price advances, locking in gains while
giving the trade room to breathe.

Components:
1. TrailingStopManager: PSAR-based or percentage-based trailing stop
2. ProgressiveROI: Time-based take-profit table that tightens over time
3. CustomStopLoss: Moves SL to break-even once profit exceeds a threshold

The trailing stop only activates after price exceeds `activation_pct` above
entry — before that, the original static SL stays in force.
"""

from typing import Any, Dict, List, Optional, Tuple
import logging
import time as _time

logger = logging.getLogger(__name__)

DEFAULT_TRAIL_PCT = 1.5
DEFAULT_ACTIVATION_PCT = 1.0
DEFAULT_STEP_PCT = 0.5


class TrailingStopManager:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.trail_pct = cfg.get("trail_pct", DEFAULT_TRAIL_PCT)
        self.activation_pct = cfg.get("activation_pct", DEFAULT_ACTIVATION_PCT)
        self.step_pct = cfg.get("step_pct", DEFAULT_STEP_PCT)
        self._high_water: Dict[int, float] = {}

    def update(
        self,
        trade_id: int,
        entry_price: float,
        current_price: float,
        original_sl: float,
        direction: str = "long",
        psar_value: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Update trailing stop for a single position.

        Returns dict with:
          - stop_loss: the effective stop-loss (may be ratcheted up)
          - trailing_active: whether trailing stop has kicked in
          - high_water: current high-water mark
          - trail_pct_used: actual trail distance from high water
          - original_sl: the original static stop-loss
        """
        if direction == "short":
            return self._update_short(trade_id, entry_price, current_price, original_sl, psar_value)

        hwm = self._high_water.get(trade_id, entry_price)
        if current_price > hwm:
            hwm = current_price
            self._high_water[trade_id] = hwm

        activation_price = entry_price * (1 + self.activation_pct / 100.0)
        trailing_active = current_price >= activation_price

        if trailing_active and psar_value is not None and psar_value > 0:
            trailing_sl = max(original_sl, psar_value)
        elif trailing_active:
            trail_dist = hwm * (self.trail_pct / 100.0)
            pct_trail = hwm - trail_dist
            trailing_sl = max(original_sl, pct_trail)
        else:
            trailing_sl = original_sl

        result = {
            "stop_loss": trailing_sl,
            "trailing_active": trailing_active,
            "high_water": hwm,
            "trail_pct_used": self.trail_pct if trailing_active else 0.0,
            "original_sl": original_sl,
        }

        if trailing_sl > original_sl:
            logger.info(
                f"[TRAILING_STOP] Trade #{trade_id}: SL ratcheted "
                f"${original_sl:.2f} → ${trailing_sl:.2f} "
                f"(HWM=${hwm:.2f}, active={trailing_active})"
            )

        return result

    def _update_short(
        self,
        trade_id: int,
        entry_price: float,
        current_price: float,
        original_sl: float,
        psar_value: Optional[float] = None,
    ) -> Dict[str, Any]:
        lwm = self._high_water.get(trade_id, entry_price)
        if current_price < lwm:
            lwm = current_price
            self._high_water[trade_id] = lwm

        activation_price = entry_price * (1 - self.activation_pct / 100.0)
        trailing_active = current_price <= activation_price

        if trailing_active and psar_value is not None and psar_value > 0:
            trailing_sl = min(original_sl, psar_value)
        elif trailing_active:
            trail_dist = lwm * (self.trail_pct / 100.0)
            pct_trail = lwm + trail_dist
            trailing_sl = min(original_sl, pct_trail)
        else:
            trailing_sl = original_sl

        return {
            "stop_loss": trailing_sl,
            "trailing_active": trailing_active,
            "high_water": lwm,
            "trail_pct_used": self.trail_pct if trailing_active else 0.0,
            "original_sl": original_sl,
        }

    def remove(self, trade_id: int) -> None:
        self._high_water.pop(trade_id, None)

    @staticmethod
    def calculate_psar(
        highs: List[float],
        lows: List[float],
        closes: List[float],
        af_start: float = 0.02,
        af_max: float = 0.20,
        af_step: float = 0.02,
    ) -> List[Optional[float]]:
        """Calculate Parabolic SAR values from OHLC data.

        Returns list of SAR values (None for insufficient data).
        Simplified PSAR: tracks extreme point + acceleration factor.
        """
        n = len(closes)
        if n < 2:
            return [None] * n

        sar_values: List[Optional[float]] = [None]
        is_long = closes[1] > closes[0]
        af = af_start
        ep = highs[1] if is_long else lows[1]
        sar = lows[0] if is_long else highs[0]

        for i in range(1, n):
            if is_long:
                sar = sar + af * (ep - sar)
                sar = min(sar, lows[i - 1])
                if i >= 2:
                    sar = min(sar, lows[i - 2])

                if lows[i] < sar:
                    is_long = False
                    sar = ep
                    ep = lows[i]
                    af = af_start
                else:
                    if highs[i] > ep:
                        ep = highs[i]
                        af = min(af + af_step, af_max)
            else:
                sar = sar + af * (ep - sar)
                sar = max(sar, highs[i - 1])
                if i >= 2:
                    sar = max(sar, highs[i - 2])

                if highs[i] > sar:
                    is_long = True
                    sar = ep
                    ep = highs[i]
                    af = af_start
                else:
                    if lows[i] < ep:
                        ep = lows[i]
                        af = min(af + af_step, af_max)

            sar_values.append(sar)

        return sar_values


# ── Progressive ROI Table ────────────────────────────────────────────────

# Default ROI table: {minutes_since_entry: profit_pct}
# With R:R=2.0, TP targets are ~3.8% (BTC) / ~4.8% (ETH).
# The table starts high to let trades reach their TP naturally,
# then steps down gradually to exit stalled positions.
# Never drops below friction (0.35%) — even dead positions must clear fees.
DEFAULT_ROI_TABLE: Dict[int, float] = {
    0: 6.0,   # Immediate: need 6% (unreachable = no instant exits)
   10: 5.0,   # 10 min: need 5% — let the trade breathe
   30: 4.0,   # 30 min: need 4% — aligns with R:R=2.0 TP target
   60: 3.0,   # 1 hour: need 3% — still above breakeven after fees
  120: 2.0,   # 2 hours: need 2% — solid profit after 0.35% friction
  240: 1.0,   # 4 hours: need 1% — trade stalled, take what's left
  480: 0.5,   # 8 hours: need 0.5% — dead position, free capital
  720: 0.35,  # 12 hours: just clear friction — stop holding dead weight
}


class ProgressiveROI:
    """Time-based take-profit table that tightens as position ages.

    At $110 capital with R:R=2.0 (TP targets ~3.8-4.8%), trades need time
    to reach their TP. Progressive ROI gives them room early (5%+ target
    in first 30 min), then steps down to exit stalled positions.
    Never drops below friction (0.35%).

    Usage:
        roi = ProgressiveROI()
        should_exit = roi.check(entry_time, current_price, entry_price)
        if should_exit:
            close_position(trade_id, current_price, "progressive_roi")
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.roi_table = cfg.get("roi_table", DEFAULT_ROI_TABLE)
        # Sort by minutes ascending for lookup
        self._sorted_minutes = sorted(self.roi_table.keys())

    def get_target_pct(self, minutes_held: int) -> float:
        """Return the ROI target % for the given minutes since entry.

        Steps down through the table: the first entry whose minutes <=
        minutes_held provides the current target.
        """
        target = self.roi_table[self._sorted_minutes[0]]
        for m in self._sorted_minutes:
            if minutes_held >= m:
                target = self.roi_table[m]
            else:
                break
        return target

    def check(
        self,
        entry_time_iso: str,
        current_price: float,
        entry_price: float,
    ) -> Tuple[bool, float, float, int]:
        """Check if the position should exit via progressive ROI.

        Returns (should_exit, current_pct, target_pct, minutes_held).
        """
        try:
            entry_dt = datetime_from_iso(entry_time_iso)
            minutes_held = int((_time.time() - entry_dt) / 60)
        except Exception:
            return False, 0.0, self.roi_table[self._sorted_minutes[0]], 0

        if entry_price <= 0:
            return False, 0.0, 0.0, minutes_held

        current_pct = (current_price - entry_price) / entry_price * 100.0
        target_pct = self.get_target_pct(minutes_held)

        should_exit = current_pct >= target_pct and current_pct > 0
        return should_exit, current_pct, target_pct, minutes_held


# ── Custom Stop-Loss Callback ─────────────────────────────────────────────

DEFAULT_BREAKEVEN_ACTIVATION_PCT = 0.5


class CustomStopLoss:
    """Moves stop-loss to break-even once unrealized profit exceeds threshold.

    At $110 capital, the default 2% SL risks $1.10 per trade. If price
    moves +0.5% in our favor, we move SL to entry price — eliminating
    risk on that position entirely. The trade either wins or breaks even.

    This stacks with TrailingStopManager:
    1. CustomStopLoss moves SL → entry (break-even) once profit ≥ 0.5%
    2. TrailingStopManager ratchets SL higher as price continues up
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.breakeven_activation_pct = cfg.get(
            "breakeven_activation_pct", DEFAULT_BREAKEVEN_ACTIVATION_PCT
        )

    def check(
        self,
        entry_price: float,
        current_price: float,
        original_sl: float,
        direction: str = "long",
    ) -> Dict[str, Any]:
        """Check if SL should be moved to break-even.

        Returns dict with:
          - stop_loss: effective SL (may be at entry = break-even)
          - breakeven_active: whether SL was moved to entry
          - unrealized_pct: current unrealized profit %
          - original_sl: the original static SL
        """
        if entry_price <= 0:
            return {
                "stop_loss": original_sl,
                "breakeven_active": False,
                "unrealized_pct": 0.0,
                "original_sl": original_sl,
            }

        if direction == "short":
            unrealized_pct = (entry_price - current_price) / entry_price * 100.0
        else:
            unrealized_pct = (current_price - entry_price) / entry_price * 100.0

        breakeven_active = unrealized_pct >= self.breakeven_activation_pct

        if breakeven_active and direction == "long":
            effective_sl = max(original_sl, entry_price)
        elif breakeven_active and direction == "short":
            effective_sl = min(original_sl, entry_price)
        else:
            effective_sl = original_sl

        return {
            "stop_loss": effective_sl,
            "breakeven_active": breakeven_active,
            "unrealized_pct": unrealized_pct,
            "original_sl": original_sl,
        }


# ── Helpers ───────────────────────────────────────────────────────────────

def datetime_from_iso(iso_str: str) -> float:
    """Parse ISO datetime string to Unix timestamp."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        # Fallback: try without timezone
        dt = datetime.fromisoformat(iso_str)
        return dt.timestamp()
