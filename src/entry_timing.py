"""
Entry Timing Module - Reversal Confirmation Logic
Prevents premature entries during mid-candle downswings.
"""

from typing import Dict, Tuple, Optional
from datetime import datetime
import logging


class EntryTimingValidator:
    """
    Validates entry timing to avoid mid-downswing purchases.

    Uses "maximum restraint" approach: Wait for price reversal confirmation
    before executing trades, even if all other conditions are met.

    Philosophy: Full context > Partial signals
    """

    def __init__(self, reversal_threshold_pct: float = 0.001):
        self.logger = logging.getLogger("EntryTimingValidator")
        self.reversal_threshold_pct = reversal_threshold_pct

        self.baseline_prices: Dict[str, float] = {}
        self.baseline_timestamps: Dict[str, datetime] = {}
        self.price_history: Dict[str, list] = {}

    def check_reversal_confirmation(
        self, symbol: str, current_price: float
    ) -> Tuple[bool, str]:
        if symbol not in self.baseline_prices:
            self.baseline_prices[symbol] = current_price
            self.baseline_timestamps[symbol] = datetime.utcnow()
            self.price_history[symbol] = [current_price]

            self.logger.info(f"[{symbol}] Baseline established at ${current_price:.2f}")
            return False, f"First cycle check - baseline ${current_price:.2f}"

        self.price_history[symbol].append(current_price)
        if len(self.price_history[symbol]) > 10:
            self.price_history[symbol].pop(0)

        baseline = self.baseline_prices[symbol]
        threshold = baseline * (1 + self.reversal_threshold_pct)

        if current_price >= threshold:
            gain_pct = ((current_price - baseline) / baseline) * 100

            self.logger.info(
                f"[{symbol}] Reversal confirmed: "
                f"${current_price:.2f} > ${threshold:.2f} "
                f"(+{gain_pct:.2f}% from baseline)"
            )

            return (
                True,
                f"Reversal confirmed: +{gain_pct:.2f}% from baseline ${baseline:.2f}",
            )

        change_pct = ((current_price - baseline) / baseline) * 100

        if current_price < baseline:
            self.logger.info(
                f"[{symbol}] Declining: ${current_price:.2f} "
                f"({change_pct:.2f}% from baseline ${baseline:.2f})"
            )
            reason = f"Price declining: {change_pct:.2f}% from baseline"
        else:
            self.logger.info(
                f"[{symbol}] Insufficient reversal: ${current_price:.2f} "
                f"(need ${threshold:.2f}, +{self.reversal_threshold_pct * 100:.1f}%)"
            )
            reason = f"Insufficient reversal: {change_pct:.2f}% (need +{self.reversal_threshold_pct * 100:.1f}%)"

        return False, reason

    def reset_baseline(self, symbol: str) -> None:
        if symbol in self.baseline_prices:
            del self.baseline_prices[symbol]
            del self.baseline_timestamps[symbol]
            self.price_history[symbol] = []
            self.logger.info(f"[{symbol}] Baseline reset")

    def get_baseline_age_seconds(self, symbol: str) -> Optional[float]:
        if symbol not in self.baseline_timestamps:
            return None

        age = (datetime.utcnow() - self.baseline_timestamps[symbol]).total_seconds()
        return age

    def get_status(self, symbol: str) -> Dict:
        if symbol not in self.baseline_prices:
            return {"baseline_set": False, "status": "waiting_for_first_check"}

        return {
            "baseline_set": True,
            "baseline_price": self.baseline_prices[symbol],
            "baseline_age_seconds": self.get_baseline_age_seconds(symbol),
            "price_history": self.price_history.get(symbol, []),
            "reversal_threshold": self.baseline_prices[symbol]
            * (1 + self.reversal_threshold_pct),
        }
