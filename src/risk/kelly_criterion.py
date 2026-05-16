"""
Kelly Criterion Position Sizing
Dynamic position sizing based on win probability and risk/reward ratio
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class KellyPositionSizer:
    """
    Calculate optimal position size using Kelly Criterion
    Formula: Kelly% = (Win_Rate * (Avg_Win / Avg_Loss) - (1 - Win_Rate)) / (Avg_Win / Avg_Loss)
    With 0.25 safety cap for real-world usage.
    """

    def __init__(
        self,
        min_position_pct: float = 0.01,
        max_position_pct: float = 0.25,
        min_trades_for_kelly: int = 20,
        default_position_pct: float = 0.10,
    ):
        self.min_position_pct = min_position_pct
        self.max_position_pct = max_position_pct
        self.min_trades_for_kelly = min_trades_for_kelly
        self.default_position_pct = default_position_pct

    def calculate_metrics_from_trades(self, trades: List[Dict]) -> Dict[str, float]:
        if not trades:
            return {
                "win_rate": 0.5,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "total_trades": 0,
            }

        wins = [t for t in trades if t.get("pnl_pct", 0) > 0]
        losses = [t for t in trades if t.get("pnl_pct", 0) <= 0]

        win_rate = len(wins) / len(trades) if trades else 0.5
        avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0.01
        avg_loss = (
            abs(sum(t["pnl_pct"] for t in losses) / len(losses)) if losses else 0.01
        )

        return {
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "total_trades": len(trades),
        }

    def calculate_kelly_pct(self, trades: List[Dict]) -> float:
        metrics = self.calculate_metrics_from_trades(trades)

        if metrics["total_trades"] < self.min_trades_for_kelly:
            return self.default_position_pct

        win_rate = metrics["win_rate"]
        avg_win = max(metrics["avg_win"], 0.0001)
        avg_loss = max(metrics["avg_loss"], 0.0001)
        win_loss_ratio = avg_win / avg_loss

        kelly = (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio

        kelly = max(kelly, self.min_position_pct)
        kelly = min(kelly, self.max_position_pct)

        return kelly

    def calculate_position_size(
        self,
        account_balance: float,
        entry_price: float,
        kelly_pct: Optional[float] = None,
        trades: Optional[List[Dict]] = None,
    ) -> float:
        if kelly_pct is None:
            if trades is None:
                kelly_pct = self.default_position_pct
            else:
                kelly_pct = self.calculate_kelly_pct(trades)

        position_value = account_balance * kelly_pct

        if entry_price > 0:
            position_size = position_value / entry_price
        else:
            position_size = 0

        return position_size
