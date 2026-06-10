"""Trading decision helper.

Provides a pure-Python function that converts enriched pre-launch token signals
into actionable trade decisions. The function does not place orders – that
responsibility belongs to the execution engine. Keeping the decision logic
side-effect free makes it easy to unit-test and safe to import.
"""

from __future__ import annotations

from typing import List, Dict, Any

__all__ = ["make_trade_decisions"]


def _symbol_from_token(token: Dict[str, Any]) -> str:
    """Return a ticker symbol for a token, falling back to a short mint."""
    ticker = token.get("ticker") or token.get("symbol")
    if ticker:
        return str(ticker).upper()
    mint = token.get("mint", "")
    return mint[:6].upper() or "UNKNOWN"


def make_trade_decisions(
    enriched_tokens: List[Dict[str, Any]], *, threshold: float = 0.5
) -> List[Dict[str, Any]]:
    """Create trade decisions from enriched token data.

    Parameters
    ----------
    enriched_tokens:
        List of token dicts as produced by PreLaunchScanner.scan_all_sources.
    threshold:
        Minimum community_score required to emit a buy decision.

    Returns
    -------
    List[Dict] with keys mint, symbol, action, priority, score.
    """
    decisions: List[Dict[str, Any]] = []
    for token in enriched_tokens:
        if "mint" not in token or "community_score" not in token:
            continue
        try:
            score = float(token["community_score"])
        except (TypeError, ValueError):
            continue
        if score < threshold:
            continue
        decisions.append(
            {
                "mint": token["mint"],
                "symbol": _symbol_from_token(token),
                "action": "buy",
                "priority": token.get("pre_launch_tier") == "HIGH_CONFIDENCE",
                "score": round(score, 3),
            }
        )
    decisions.sort(key=lambda d: d["score"], reverse=True)
    return decisions