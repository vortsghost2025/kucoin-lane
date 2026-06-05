"""
Micro-Account Edge Gate
========================
Rejects trades that cannot clear round-trip friction at $110 capital.

Rules:
1. expected_edge_pct < fee_pct + spread_pct + slippage_pct + safety_margin_pct -> REJECT
2. expected_profit_usd < MIN_PROFIT_USD -> REJECT
3. position_size_usd < min_notional_usd -> REJECT
4. spread_pct > max_spread_pct -> REJECT
5. projected_loss_usd > max_trade_loss_usd -> REJECT

Fee model:
  KuCoin spot base: 0.1% taker/maker
  Round-trip minimum: 0.2% (entry + exit)
  Add spread + slippage + safety margin for real-world friction
"""

from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

DEFAULT_FEE_RATE = 0.001
DEFAULT_ROUND_TRIP_FEE_PCT = 0.20
DEFAULT_SLIPPAGE_PCT = 0.05
DEFAULT_SAFETY_MARGIN_PCT = 0.10
DEFAULT_MIN_PROFIT_USD = 0.25
DEFAULT_MAX_SPREAD_PCT = 1.0
DEFAULT_MIN_EDGE_PCT = 0.40


class EdgeGateResult:
    __slots__ = ("approved", "rejection_reason", "fee_pct", "spread_pct",
                 "slippage_pct", "safety_margin_pct", "total_friction_pct",
                 "expected_edge_pct", "expected_profit_usd")

    def __init__(self, approved: bool, rejection_reason: str = "", **kwargs):
        self.approved = approved
        self.rejection_reason = rejection_reason
        self.fee_pct = kwargs.get("fee_pct", 0.0)
        self.spread_pct = kwargs.get("spread_pct", 0.0)
        self.slippage_pct = kwargs.get("slippage_pct", 0.0)
        self.safety_margin_pct = kwargs.get("safety_margin_pct", 0.0)
        self.total_friction_pct = kwargs.get("total_friction_pct", 0.0)
        self.expected_edge_pct = kwargs.get("expected_edge_pct", 0.0)
        self.expected_profit_usd = kwargs.get("expected_profit_usd", 0.0)


class EdgeGate:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        self.fee_rate = cfg.get("fee_rate", DEFAULT_FEE_RATE)
        self.round_trip_fee_pct = cfg.get("round_trip_fee_pct", DEFAULT_ROUND_TRIP_FEE_PCT)
        self.slippage_pct = cfg.get("slippage_pct", DEFAULT_SLIPPAGE_PCT)
        self.safety_margin_pct = cfg.get("safety_margin_pct", DEFAULT_SAFETY_MARGIN_PCT)
        self.min_profit_usd = cfg.get("min_profit_usd", DEFAULT_MIN_PROFIT_USD)
        self.max_spread_pct = cfg.get("max_spread_pct", DEFAULT_MAX_SPREAD_PCT)
        self.min_edge_pct = cfg.get("min_edge_pct", DEFAULT_MIN_EDGE_PCT)
        self.min_notional_usd = cfg.get("min_notional_usd", 5.0)
        self.max_trade_loss_usd = cfg.get("max_trade_loss_usd", 1.10)

    def evaluate(
        self,
        expected_edge_pct: float,
        position_size_usd: float,
        spread_pct: float = 0.0,
        take_profit_pct: float = 0.0,
        stop_loss_pct: float = 0.0,
        pair: str = "",
    ) -> EdgeGateResult:
        total_friction = (
            self.round_trip_fee_pct
            + spread_pct
            + self.slippage_pct
            + self.safety_margin_pct
        )

        expected_profit_usd = position_size_usd * (expected_edge_pct / 100.0)
        projected_loss_usd = position_size_usd * (stop_loss_pct / 100.0) if stop_loss_pct > 0 else 0.0

        kwargs = {
            "fee_pct": self.round_trip_fee_pct,
            "spread_pct": spread_pct,
            "slippage_pct": self.slippage_pct,
            "safety_margin_pct": self.safety_margin_pct,
            "total_friction_pct": total_friction,
            "expected_edge_pct": expected_edge_pct,
            "expected_profit_usd": expected_profit_usd,
        }

        if position_size_usd < self.min_notional_usd:
            reason = (
                f"Position notional ${position_size_usd:.2f} below "
                f"minimum ${self.min_notional_usd:.2f}"
            )
            logger.info(f"[EDGE_GATE] REJECT {pair}: {reason}")
            return EdgeGateResult(False, reason, **kwargs)

        if spread_pct > self.max_spread_pct:
            reason = (
                f"Spread {spread_pct:.2f}% exceeds max {self.max_spread_pct:.2f}%"
            )
            logger.info(f"[EDGE_GATE] REJECT {pair}: {reason}")
            return EdgeGateResult(False, reason, **kwargs)

        if expected_edge_pct < total_friction:
            reason = (
                f"Edge {expected_edge_pct:.2f}% < friction {total_friction:.2f}% "
                f"(fee={self.round_trip_fee_pct:.2f}% + spread={spread_pct:.2f}% "
                f"+ slip={self.slippage_pct:.2f}% + margin={self.safety_margin_pct:.2f}%)"
            )
            logger.info(f"[EDGE_GATE] REJECT {pair}: {reason}")
            return EdgeGateResult(False, reason, **kwargs)

        if expected_edge_pct < self.min_edge_pct:
            reason = (
                f"Edge {expected_edge_pct:.2f}% below minimum "
                f"{self.min_edge_pct:.2f}% (after friction)"
            )
            logger.info(f"[EDGE_GATE] REJECT {pair}: {reason}")
            return EdgeGateResult(False, reason, **kwargs)

        if expected_profit_usd < self.min_profit_usd:
            reason = (
                f"Expected profit ${expected_profit_usd:.4f} below "
                f"minimum ${self.min_profit_usd:.2f}"
            )
            logger.info(f"[EDGE_GATE] REJECT {pair}: {reason}")
            return EdgeGateResult(False, reason, **kwargs)

        if projected_loss_usd > self.max_trade_loss_usd:
            reason = (
                f"Projected loss ${projected_loss_usd:.2f} exceeds "
                f"max ${self.max_trade_loss_usd:.2f}"
            )
            logger.info(f"[EDGE_GATE] REJECT {pair}: {reason}")
            return EdgeGateResult(False, reason, **kwargs)

        net_edge_pct = expected_edge_pct - total_friction
        logger.info(
            f"[EDGE_GATE] APPROVE {pair}: edge={expected_edge_pct:.2f}% "
            f"friction={total_friction:.2f}% net={net_edge_pct:.2f}% "
            f"profit=${expected_profit_usd:.4f}"
        )
        return EdgeGateResult(True, "", **kwargs)

    def evaluate_take_profit(
        self,
        take_profit_pct: float,
        position_size_usd: float,
        spread_pct: float = 0.0,
        pair: str = "",
    ) -> EdgeGateResult:
        return self.evaluate(
            expected_edge_pct=take_profit_pct,
            position_size_usd=position_size_usd,
            spread_pct=spread_pct,
            take_profit_pct=take_profit_pct,
            pair=pair,
        )
