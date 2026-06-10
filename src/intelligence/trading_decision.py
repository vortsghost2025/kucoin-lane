"""
Trading Decision Module for the "first penny" pipeline.

Converts enriched pre-launch token signals (from PreLaunchScanner / NewTokenFeed)
into actionable buy decisions using creator reputation/boost.

Integrates with:
- CreatorTracker / get_creator_boost for reputation scoring.
- Pre-launch community scores.
- Simple risk rules for the initial live loop.

Used by run_pipeline.py for both DEX pre-launch watchlists and KuCoin signals.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from integrate_creator_intel import get_creator_boost
from .chain.token_models import TokenInfo


@dataclass
class TradeDecision:
    token: TokenInfo
    action: str  # "BUY", "WATCH", "SKIP"
    confidence: float
    boost: float
    reason: str
    suggested_size_pct: float = 0.01  # 1% of capital for first penny


def make_trade_decisions(
    tokens: List[TokenInfo],
    min_community_score: float = 0.3,
    min_boost: float = 1.0,
    max_positions: int = 3,
    current_positions: int = 0,
) -> List[TradeDecision]:
    """
    Core function: turn a list of fresh pre-launch / new tokens into trade decisions.

    Applies:
    - Creator boost from integrate_creator_intel (uses creator_registry.json).
    - Community score filter.
    - Simple position limit.
    - Returns prioritized list of BUY/WATCH/SKIP decisions.
    """
    decisions: List[TradeDecision] = []

    for token in tokens:
        creator = token.creator or "unknown"
        boost = get_creator_boost(creator)

        community = token.community_score
        tier = token.pre_launch_tier

        if current_positions >= max_positions:
            action = "SKIP"
            reason = "max_positions_reached"
            confidence = 0.0
        elif community < min_community_score:
            action = "SKIP"
            reason = f"low_community_score={community:.2f}"
            confidence = community
        elif boost < min_boost:
            action = "WATCH"
            reason = f"boost={boost:.2f} below threshold"
            confidence = min(0.6, community + (boost - 1.0))
        else:
            action = "BUY"
            reason = f"creator_boost={boost:.2f}, community={community:.2f}, tier={tier}"
            confidence = min(0.95, (community + (boost - 1.0)) / 2)

        suggested_size = 0.01 if action == "BUY" else 0.0

        decisions.append(
            TradeDecision(
                token=token,
                action=action,
                confidence=round(confidence, 3),
                boost=boost,
                reason=reason,
                suggested_size_pct=suggested_size,
            )
        )

    # Sort BUY first, then by confidence
    decisions.sort(key=lambda d: (0 if d.action == "BUY" else 1 if d.action == "WATCH" else 2, -d.confidence))
    return decisions


def decisions_to_watchlist(decisions: List[TradeDecision]) -> List[Dict[str, Any]]:
    """Convert decisions to a simple watchlist for monitoring DEX listings."""
    return [
        {
            "mint": d.token.mint,
            "ticker": d.token.ticker,
            "action": d.action,
            "confidence": d.confidence,
            "boost": d.boost,
            "reason": d.reason,
            "creator": d.token.creator,
        }
        for d in decisions
        if d.action in ("BUY", "WATCH")
    ]
