"""Prometheus metrics for KuCoin Lane."""

from prometheus_client import Gauge, Counter


def _label_value(value: str, max_len: int = 64) -> str:
    text = str(value or "unknown")
    return text[:max_len]

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


# Counter: cumulative live token creation events processed from websocket/webhooks.
live_token_events_total = Counter(
    "live_token_events_total",
    "Cumulative count of live token creation events processed.",
    ["source", "factory"],
)

# Gauge: latest externally boosted creator reputation for an observed live token.
live_creator_reputation_score = Gauge(
    "live_creator_reputation_score",
    "Latest externally enriched creator reputation score for a live token event.",
    ["creator", "mint", "symbol", "tags"],
)

# Counter: high-frequency/serial/alpha creator launches surfaced for alerting.
high_frequency_creator_launches_total = Counter(
    "high_frequency_creator_launches_total",
    "Cumulative live launches from creators tagged high_frequency, serial_launcher, or alpha.",
    ["creator", "tag"],
)


def record_live_creator_event(
    source: str,
    factory: str,
    mint: str,
    symbol: str,
    creator: str,
    reputation_score: float,
    tags: list,
) -> None:
    """Record live creator telemetry for Prometheus and dashboards."""
    tag_values = [str(tag) for tag in tags if tag]
    tag_label = ",".join(tag_values) or "none"

    live_token_events_total.labels(
        source=_label_value(source),
        factory=_label_value(factory),
    ).inc()
    live_creator_reputation_score.labels(
        creator=_label_value(creator),
        mint=_label_value(mint),
        symbol=_label_value(symbol, max_len=24),
        tags=_label_value(tag_label, max_len=128),
    ).set(float(reputation_score or 0.0))

    for alert_tag in ("serial_launcher", "high_frequency", "alpha"):
        if alert_tag in tag_values:
            high_frequency_creator_launches_total.labels(
                creator=_label_value(creator),
                tag=alert_tag,
            ).inc()
