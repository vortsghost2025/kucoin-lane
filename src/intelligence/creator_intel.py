"""Creator Intelligence Integration Helper
=======================================
Provides functions to integrate creator intelligence into trading signals.
"""

import json
import logging
from pathlib import Path


def get_creator_boost(token_symbol: str) -> float:
    """
    Get the creator reputation score for a given token symbol.

    Args:
        token_symbol: The token symbol (e.g., 'ABC')

    Returns:
        float: Creator reputation score between 0.0 and 1.0, or 0.0 if not found
    """
    try:
        registry_path = Path("data/creator_registry.json")
        if not registry_path.exists():
            return 0.0

        with open(registry_path) as f:
            registry = json.load(f)

        # Defensive: ensure registry is a dict (could be corrupted list)
        if not isinstance(registry, dict):
            logging.warning(f"Creator registry is not a dict (type: {type(registry).__name__}), skipping creator boost")
            return 0.0

        # Search for creator by token in their history
        for creator_id, profile in registry.items():
            for token_entry in profile.get("token_history", []):
                if token_entry.get("token") == token_symbol:
                    return profile.get("reputation_score", 0.0)

        return 0.0
    except Exception as e:
        logging.warning(f"Failed to get creator boost for {token_symbol}: {e}")
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