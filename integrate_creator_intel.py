"""Creator Intelligence Integration Helper (re-export)
=====================================================
Backward-compatible wrapper that re-exports from src.intelligence.creator_intel.
"""

from src.intelligence.creator_intel import get_creator_boost, enrich_signal_with_creator

__all__ = ["get_creator_boost", "enrich_signal_with_creator"]