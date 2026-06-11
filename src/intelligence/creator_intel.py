"""Creator Intelligence Integration Helper
=======================================
Provides functions to integrate creator intelligence into trading signals.
"""

import json
import logging
from pathlib import Path


def get_creator_boost(lookup: str) -> float:
    """
    Get the creator reputation score for a given token symbol or creator wallet ID.

    Handles two calling conventions:
    1. Creator wallet ID (from trading_decision.py, orchestrator.py)
    2. Token symbol (from enrich_signal_with_creator)

    Args:
        lookup: Token symbol OR creator wallet ID

    Returns:
        float: Creator reputation score between 0.0 and 1.0, or 0.0 if not found
    """
    try:
        registry_path = Path(__file__).resolve().parent.parent.parent / "data" / "creator_registry.json"
        if not registry_path.exists():
            return 0.0

        with open(registry_path) as f:
            registry = json.load(f)

        # Defensive: ensure registry is a dict (could be corrupted list)
        if not isinstance(registry, dict):
            logging.warning(f"Creator registry is not a dict (type: {type(registry).__name__}), skipping creator boost")
            return 0.0

        # Fast path: direct creator_id lookup (wallet address passed from trading_decision/orchestrator)
        profile = registry.get(lookup)
        if profile and isinstance(profile, dict):
            boost = profile.get("reputation_score") or profile.get("score") or 0.0
            return min(1.0, max(0.0, boost))

        # Fallback: search by token symbol in creator histories
        for creator_id, p in registry.items():
            if creator_id == "unknown" or not isinstance(p, dict):
                continue
            for token_entry in p.get("token_history", []):
                if token_entry.get("token") == lookup:
                    boost = p.get("reputation_score") or p.get("score") or 0.0
                    return min(1.0, max(0.0, boost))

        return 0.0
    except Exception as e:
        logging.warning(f"Failed to get creator boost for {lookup}: {e}")
        return 0.0


def enrich_signal_with_creator(signal: dict, token_symbol: str) -> dict:
    """
    Enrich a trading signal with creator intelligence.

    Args:
        signal: The original signal dictionary
        token_symbol: The token symbol to look up

    Returns:
        dict: The signal enriched with creator information
    """
    try:
        creator_score = get_creator_boost(token_symbol)
        enriched = signal.copy()
        enriched["creator_score"] = creator_score
        enriched["creator_boost_applied"] = creator_score > 0.0

        if creator_score > 0.7:
            enriched["creator_tier"] = "alpha"
        elif creator_score > 0.4:
            enriched["creator_tier"] = "established"
        else:
            enriched["creator_tier"] = "unknown"

        return enriched
    except Exception as e:
        logging.warning(f"Failed to enrich signal for {token_symbol}: {e}")
        return signal
