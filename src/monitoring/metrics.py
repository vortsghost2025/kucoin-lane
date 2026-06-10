"""Prometheus metrics for KuCoin Lane.

This module defines gauges that can be scraped by a Prometheus server.
Only a minimal set is required for the current task – a gauge tracking
how many creator‑boost adjustments were applied in the current cycle.
"""

from prometheus_client import Gauge, Counter

# Gauge: total creator boosts applied in the current cycle.
# This gauge is set at the end of each orchestrator cycle.
creator_boosts_total = Gauge(
    "creator_boosts_total",
    "Number of creator boost adjustments applied in the current cycle",
)

def set_creator_boosts(value: int) -> None:
    """Update the Prometheus gauge with the provided value.

    Args:
        value: Integer count of creator boosts applied.
    """
    creator_boosts_total.set(value)

# -------------------------------------------------------------------------
# New metrics for creator‑tracking (the pieces that were missing)
# -------------------------------------------------------------------------

# Gauge: how many distinct creator addresses are currently known
active_creators_total = Gauge(
    "active_creators_total",
    "How many distinct token‑creating addresses are currently tracked.",
)

# Counter: cumulative number of *new* creators discovered over the lifetime of the process
creator_discoveries_total = Counter(
    "creator_discoveries_total",
    "Cumulative count of unique creators discovered over time.",
)

def set_active_creators(value: int) -> None:
    """Set the gauge to the current count of distinct creators."""
    active_creators_total.set(value)

def inc_creator_discoveries(delta: int = 1) -> None:
    """Increment the discovery counter – called once per newly‑seen creator."""
    creator_discoveries_total.inc(delta)
