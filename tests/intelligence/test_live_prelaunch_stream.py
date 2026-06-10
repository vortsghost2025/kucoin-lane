"""Tests for live pre-launch streaming and creator intelligence boost."""

from pathlib import Path

from prometheus_client import generate_latest

from src.monitoring.metrics import record_live_creator_event
from src.intelligence.creator_tracker import CreatorTrackerAgent
from src.intelligence.live_prelaunch_stream import (
    ExternalCreatorIntelligence,
    LivePreLaunchEventProcessor,
    normalize_token_creation_event,
)


class StubTracker:
    def __init__(self):
        self.calls = []

    def execute(self, input_data):
        self.calls.append(input_data)
        token = input_data["pumpfun_tokens"][0]
        return {
            "success": True,
            "data": {
                "new_creators": [
                    {
                        "token": token["ticker"],
                        "creator": token["creator"],
                        "factory": token["factory"],
                    }
                ],
                "creator_count": 1,
                "alpha_count": 1,
                "updated_profiles": [token["creator"]],
            },
        }


class StubIntelligence:
    def enrich_token(self, token):
        enriched = dict(token)
        enriched["creator_reputation"] = 0.82
        enriched["creator_tags"] = ["serial_launcher", "alpha"]
        enriched["external_creator_intelligence"] = {
            "source_names": ["birdeye", "dexscreener"],
            "historical_token_count": 12,
            "cross_wallet_hits": 2,
        }
        return enriched


class StubMetrics:
    def __init__(self):
        self.events = []

    def record_live_creator_event(self, **kwargs):
        self.events.append(kwargs)


class StubBirdeye:
    def token_overview(self, mint):
        return {
            "address": mint,
            "creator": "creator_wallet",
            "creator_token_count": 8,
            "cross_wallet_count": 2,
            "liquidity": 18_000,
            "volume_24h": 60_000,
            "twitter": "https://x.com/example",
        }


class StubDexScreener:
    def get_token(self, chain_id, token_address):
        return {
            "chainId": chain_id,
            "pairAddress": "pair1",
            "liquidity": {"usd": 24_000},
            "volume": {"h24": 80_000},
            "info": {"socials": [{"type": "telegram", "url": "https://t.me/example"}]},
        }

    def search(self, query):
        return [
            {"baseToken": {"address": "MintA"}, "liquidity": {"usd": 10_000}},
            {"baseToken": {"address": "MintB"}, "liquidity": {"usd": 8_000}},
        ]


def test_normalize_token_creation_event_accepts_helius_style_payload():
    event = {
        "source": "helius_websocket",
        "signature": "sig123",
        "token": {"mint": "Mint111", "symbol": "MINTY"},
        "creator": "creator_wallet",
        "factory": "pump_fun",
    }

    token = normalize_token_creation_event(event)

    assert token["mint"] == "Mint111"
    assert token["ticker"] == "MINTY"
    assert token["creator"] == "creator_wallet"
    assert token["factory"] == "pump_fun"
    assert token["source"] == "helius_websocket"
    assert token["signature"] == "sig123"


def test_external_creator_intelligence_scores_serial_creator_before_tracker():
    intelligence = ExternalCreatorIntelligence(
        birdeye=StubBirdeye(),
        dexscreener=StubDexScreener(),
    )

    token = {
        "mint": "Mint111",
        "ticker": "MINTY",
        "creator": "creator_wallet",
        "community_score": 0.2,
        "creator_reputation": 0.0,
    }

    enriched = intelligence.enrich_token(token)

    assert enriched["creator_reputation"] >= 0.6
    assert "serial_launcher" in enriched["creator_tags"]
    assert "alpha" in enriched["creator_tags"]
    assert enriched["external_creator_intelligence"]["historical_token_count"] >= 8
    assert enriched["external_creator_intelligence"]["cross_wallet_hits"] == 2


def test_live_processor_enriches_and_tracks_event(tmp_path: Path):
    tracker = StubTracker()
    metrics = StubMetrics()
    processor = LivePreLaunchEventProcessor(
        tracker=tracker,
        intelligence=StubIntelligence(),
        metrics=metrics,
        output_dir=tmp_path,
    )

    result = processor.process_event(
        {
            "source": "helius_websocket",
            "mint": "Mint111",
            "ticker": "MINTY",
            "creator": "creator_wallet",
            "factory": "pump_fun",
            "signature": "sig123",
        }
    )

    assert result["success"] is True
    assert tracker.calls[0]["pumpfun_tokens"][0]["creator_reputation"] == 0.82
    assert tracker.calls[0]["pumpfun_tokens"][0]["creator_tags"] == ["serial_launcher", "alpha"]
    assert metrics.events[0]["creator"] == "creator_wallet"
    assert metrics.events[0]["reputation_score"] == 0.82
    assert metrics.events[0]["tags"] == ["serial_launcher", "alpha"]
    assert (tmp_path / "latest_live_prelaunch.json").exists()


def test_record_live_creator_event_exposes_prometheus_series():
    record_live_creator_event(
        source="helius_websocket",
        factory="pump_fun",
        mint="Mint111",
        symbol="MINTY",
        creator="creator_wallet",
        reputation_score=0.82,
        tags=["serial_launcher", "alpha"],
    )

    metrics_output = generate_latest().decode()

    assert 'live_token_events_total{factory="pump_fun",source="helius_websocket"}' in metrics_output
    assert 'live_creator_reputation_score{creator="creator_wallet",mint="Mint111",symbol="MINTY",tags="serial_launcher,alpha"} 0.82' in metrics_output
    assert 'high_frequency_creator_launches_total{creator="creator_wallet",tag="serial_launcher"}' in metrics_output


def test_creator_tracker_uses_external_reputation_for_new_pumpfun_creator(tmp_path: Path):
    db_path = tmp_path / "creator_registry.json"
    agent = CreatorTrackerAgent({"creator_db_path": str(db_path)})

    result = agent.execute(
        {
            "pumpfun_tokens": [
                {
                    "mint": "Mint111111111111111111111111111111111",
                    "ticker": "MINTY",
                    "name": "Minty",
                    "creator": "creator_wallet",
                    "factory": "pump_fun",
                    "created_at": "2026-06-10T00:00:00Z",
                    "community_score": 0.2,
                    "creator_reputation": 0.82,
                    "creator_tags": ["serial_launcher", "alpha"],
                    "external_creator_intelligence": {"historical_token_count": 12},
                }
            ]
        }
    )

    profile = agent.creator_profiles["creator_wallet"]
    assert result["success"] is True
    assert profile.reputation_score == 0.82
    assert "serial_launcher" in profile.tags
    assert "alpha" in profile.tags
    assert profile.performance_metrics["external_historical_token_count"] == 12
