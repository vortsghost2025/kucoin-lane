"""Live pre-launch token stream processing.

This module separates the testable event-processing path from the websocket
transport. The processor accepts normalized token-creation events, enriches the
creator before the initial reputation score is assigned, then hands the event to
CreatorTrackerAgent.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterable, Dict, List, Optional

import websockets

from src.data.dex_intelligence.birdeye import BirdeyeProvider
from src.data.dex_intelligence.dexscreener import DexScreenerProvider
from src.intelligence.chain.helius_provider import HeliusProvider
from src.intelligence.creator_tracker import CreatorTrackerAgent, DEFAULT_FACTORY_ADDRESSES
from src.monitoring import metrics as prometheus_metrics

logger = logging.getLogger(__name__)


PUMPFUN_PROGRAM_ID = DEFAULT_FACTORY_ADDRESSES["pump_fun"]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default


def _append_unique(items: List[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _first_present(data: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize_token_creation_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize webhook/websocket token creation payloads into tracker input."""
    token = event.get("token") or event.get("token_data") or event.get("baseToken") or {}
    if not isinstance(token, dict):
        token = {}

    mint = _first_present(
        event,
        ["mint", "address", "token_address", "tokenAddress", "base_token_address"],
    ) or _first_present(token, ["mint", "address", "tokenAddress"])
    creator = _first_present(
        event,
        ["creator", "deployer", "creator_wallet", "creatorWallet", "fee_payer", "feePayer"],
    ) or _first_present(token, ["creator", "deployer"])
    ticker = _first_present(event, ["ticker", "symbol"]) or _first_present(token, ["ticker", "symbol"])
    name = _first_present(event, ["name"]) or _first_present(token, ["name"])

    if not ticker and mint:
        ticker = str(mint)[:8].upper()

    source = event.get("source", "live_stream")
    factory = event.get("factory") or event.get("dex") or "pump_fun"
    program_id = event.get("program_id", event.get("programId", ""))
    if program_id == PUMPFUN_PROGRAM_ID:
        factory = "pump_fun"

    social_links = event.get("social_links") or event.get("socialLinks") or {}
    if not isinstance(social_links, dict):
        social_links = {}

    return {
        "name": name or ticker or "",
        "ticker": ticker or "",
        "mint": mint or "",
        "description": event.get("description", ""),
        "creator": creator or "",
        "market_cap_usd": _as_float(event.get("market_cap_usd", event.get("marketCap", 0.0))),
        "created_at": event.get("created_at") or event.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        "social_links": social_links,
        "n_social_platforms": len(social_links),
        "launch_platforms": event.get("launch_platforms", []),
        "creator_reputation": _as_float(event.get("creator_reputation", 0.0)),
        "community_score": _as_float(event.get("community_score", 0.0)),
        "pre_launch_tier": event.get("pre_launch_tier", "NOISE"),
        "factory": factory,
        "source": source,
        "signature": event.get("signature", ""),
        "program_id": program_id,
    }


def extract_token_creation_from_transaction(transaction: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract creator and mint from a Helius getTransaction result."""
    if not transaction:
        return {}

    message = transaction.get("transaction", {}).get("message", {})
    account_keys = message.get("accountKeys", [])
    creator = ""
    if account_keys:
        first_key = account_keys[0]
        creator = first_key.get("pubkey", "") if isinstance(first_key, dict) else str(first_key)

    mint = ""
    meta = transaction.get("meta", {})
    for balance in meta.get("postTokenBalances", []) or []:
        mint = balance.get("mint", "")
        if mint:
            break

    if not mint:
        for instruction in message.get("instructions", []) or []:
            parsed = instruction.get("parsed", {}) if isinstance(instruction, dict) else {}
            info = parsed.get("info", {}) if isinstance(parsed, dict) else {}
            mint = info.get("mint", "")
            if mint:
                break

    return {"mint": mint, "creator": creator}


class ExternalCreatorIntelligence:
    """Immediate Birdeye/DexScreener reputation enrichment for new creators."""

    def __init__(
        self,
        birdeye: Optional[Any] = None,
        dexscreener: Optional[Any] = None,
        chain: str = "solana",
    ):
        self.chain = chain
        self.birdeye = birdeye if birdeye is not None else BirdeyeProvider(chain=chain)
        self.dexscreener = dexscreener if dexscreener is not None else DexScreenerProvider(chain=chain)

    def enrich_token(self, token: Dict[str, Any]) -> Dict[str, Any]:
        """Attach external creator reputation before tracker profile creation."""
        enriched = dict(token)
        mint = enriched.get("mint", "")
        creator = enriched.get("creator", "")
        if not mint and not creator:
            return enriched

        report = self._build_report(mint=mint, creator=creator)
        base_reputation = _as_float(enriched.get("creator_reputation", 0.0))
        enriched["creator_reputation"] = round(max(base_reputation, report["reputation_score"]), 4)
        enriched["creator_tags"] = self._merge_tags(enriched.get("creator_tags", []), report["tags"])
        enriched["external_creator_intelligence"] = report
        return enriched

    def _build_report(self, mint: str, creator: str) -> Dict[str, Any]:
        source_names: List[str] = []
        historical_token_count = 0
        cross_wallet_hits = 0
        max_liquidity = 0.0
        max_volume = 0.0
        social_count = 0

        birdeye_data = self._safe_birdeye_overview(mint)
        if birdeye_data:
            source_names.append("birdeye")
            historical_token_count = max(historical_token_count, self._extract_token_count(birdeye_data))
            cross_wallet_hits = max(cross_wallet_hits, self._extract_cross_wallet_hits(birdeye_data))
            max_liquidity = max(max_liquidity, _as_float(birdeye_data.get("liquidity")))
            max_volume = max(max_volume, _as_float(birdeye_data.get("volume_24h", birdeye_data.get("volume24h"))))
            social_count = max(social_count, self._count_social_links(birdeye_data))

        dex_pair = self._safe_dex_pair(mint)
        if dex_pair:
            source_names.append("dexscreener")
            liquidity = dex_pair.get("liquidity", {}) if isinstance(dex_pair.get("liquidity"), dict) else {}
            volume = dex_pair.get("volume", {}) if isinstance(dex_pair.get("volume"), dict) else {}
            max_liquidity = max(max_liquidity, _as_float(liquidity.get("usd")))
            max_volume = max(max_volume, _as_float(volume.get("h24")))
            social_count = max(social_count, self._count_dex_socials(dex_pair))

        dex_history = self._safe_dex_search(creator)
        if dex_history:
            if "dexscreener" not in source_names:
                source_names.append("dexscreener")
            historical_token_count = max(historical_token_count, self._count_unique_dex_tokens(dex_history))

        reputation_score = self._score_report(
            historical_token_count=historical_token_count,
            cross_wallet_hits=cross_wallet_hits,
            max_liquidity=max_liquidity,
            max_volume=max_volume,
            social_count=social_count,
            source_count=len(source_names),
        )

        return {
            "creator": creator,
            "token_mint": mint,
            "source_names": source_names,
            "historical_token_count": historical_token_count,
            "cross_wallet_hits": cross_wallet_hits,
            "max_liquidity_usd": round(max_liquidity, 4),
            "max_volume_24h_usd": round(max_volume, 4),
            "social_count": social_count,
            "reputation_score": reputation_score,
            "tags": self._tags_for_report(historical_token_count, reputation_score),
        }

    def _safe_birdeye_overview(self, mint: str) -> Dict[str, Any]:
        if not mint or not self.birdeye:
            return {}
        try:
            return self.birdeye.token_overview(mint) or {}
        except Exception as exc:
            logger.debug("Birdeye creator intelligence failed for %s: %s", mint, exc)
            return {}

    def _safe_dex_pair(self, mint: str) -> Dict[str, Any]:
        if not mint or not self.dexscreener:
            return {}
        try:
            return self.dexscreener.get_token(self.chain, mint) or {}
        except Exception as exc:
            logger.debug("DexScreener token lookup failed for %s: %s", mint, exc)
            return {}

    def _safe_dex_search(self, creator: str) -> List[Dict[str, Any]]:
        if not creator or not self.dexscreener:
            return []
        try:
            return self.dexscreener.search(creator) or []
        except Exception as exc:
            logger.debug("DexScreener creator search failed for %s: %s", creator, exc)
            return []

    @staticmethod
    def _extract_token_count(data: Dict[str, Any]) -> int:
        count_fields = [
            "creator_token_count",
            "deployer_token_count",
            "created_tokens",
            "token_count",
            "launch_count",
            "total_tokens",
        ]
        direct = max(_as_int(data.get(field)) for field in count_fields)
        token_lists = [data.get("creator_tokens"), data.get("tokens"), data.get("launches")]
        list_count = max((len(items) for items in token_lists if isinstance(items, list)), default=0)
        return max(direct, list_count)

    @staticmethod
    def _extract_cross_wallet_hits(data: Dict[str, Any]) -> int:
        direct = max(
            _as_int(data.get("cross_wallet_count")),
            _as_int(data.get("linked_wallet_count")),
            _as_int(data.get("wallet_cluster_size")),
        )
        linked_lists = [data.get("linked_wallets"), data.get("wallets"), data.get("creator_wallets")]
        list_count = max((len(items) for items in linked_lists if isinstance(items, list)), default=0)
        return max(direct, list_count)

    @staticmethod
    def _count_social_links(data: Dict[str, Any]) -> int:
        count = 0
        for field in ("website", "telegram", "twitter", "discord"):
            if data.get(field):
                count += 1
        social_links = data.get("social_links", {})
        if isinstance(social_links, dict):
            count = max(count, sum(1 for value in social_links.values() if value))
        return count

    @staticmethod
    def _count_dex_socials(pair: Dict[str, Any]) -> int:
        info = pair.get("info", {}) if isinstance(pair.get("info"), dict) else {}
        socials = info.get("socials", [])
        websites = info.get("websites", [])
        total = 0
        if isinstance(socials, list):
            total += len([item for item in socials if item])
        if isinstance(websites, list):
            total += len([item for item in websites if item])
        return total

    @staticmethod
    def _count_unique_dex_tokens(pairs: List[Dict[str, Any]]) -> int:
        tokens = set()
        for pair in pairs:
            base = pair.get("baseToken", {}) if isinstance(pair.get("baseToken"), dict) else {}
            token_address = base.get("address") or pair.get("tokenAddress")
            if token_address:
                tokens.add(token_address)
        return len(tokens)

    @staticmethod
    def _score_report(
        historical_token_count: int,
        cross_wallet_hits: int,
        max_liquidity: float,
        max_volume: float,
        social_count: int,
        source_count: int,
    ) -> float:
        score = 0.0
        if historical_token_count >= 10:
            score += 0.45
        elif historical_token_count >= 5:
            score += 0.35
        elif historical_token_count >= 2:
            score += 0.20

        if cross_wallet_hits >= 2:
            score += 0.20
        elif cross_wallet_hits >= 1:
            score += 0.10

        if max_liquidity >= 10_000:
            score += 0.10
        if max_volume >= 50_000:
            score += 0.10
        if social_count >= 2:
            score += 0.10
        elif social_count >= 1:
            score += 0.05
        if source_count >= 2:
            score += 0.05

        return round(min(1.0, score), 4)

    @staticmethod
    def _tags_for_report(historical_token_count: int, reputation_score: float) -> List[str]:
        tags: List[str] = []
        if historical_token_count >= 3:
            tags.append("high_frequency")
        if historical_token_count >= 5:
            tags.append("serial_launcher")
        if reputation_score >= 0.8:
            tags.append("alpha")
        elif reputation_score >= 0.55:
            tags.append("repeat")
        return tags

    @staticmethod
    def _merge_tags(existing: Any, new_tags: List[str]) -> List[str]:
        merged: List[str] = []
        if isinstance(existing, list):
            for tag in existing:
                _append_unique(merged, str(tag))
        for tag in new_tags:
            _append_unique(merged, tag)
        return merged


class LivePreLaunchEventProcessor:
    """Process live token-creation events through creator intelligence."""

    def __init__(
        self,
        tracker: Optional[Any] = None,
        intelligence: Optional[Any] = None,
        metrics: Optional[Any] = None,
        output_dir: Path = Path("data"),
    ):
        self.tracker = tracker or CreatorTrackerAgent({"creator_db_path": "data/creator_registry.json"})
        self.intelligence = intelligence or ExternalCreatorIntelligence()
        self.metrics = metrics or prometheus_metrics
        self.output_dir = Path(output_dir)

    def process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        token = normalize_token_creation_event(event)
        if not token.get("mint"):
            return {"success": False, "reason": "missing_mint", "event": event}
        if not token.get("creator"):
            return {"success": False, "reason": "missing_creator", "token": token}

        enriched_token = self.intelligence.enrich_token(token)
        tracker_result = self.tracker.execute({"pumpfun_tokens": [enriched_token]})

        reputation = _as_float(enriched_token.get("creator_reputation", 0.0))
        tags = enriched_token.get("creator_tags", [])
        if not isinstance(tags, list):
            tags = []

        summary = {
            "success": bool(tracker_result.get("success")),
            "phase": "live_prelaunch",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": enriched_token.get("source", "live_stream"),
            "factory": enriched_token.get("factory", "pump_fun"),
            "mint": enriched_token.get("mint", ""),
            "symbol": enriched_token.get("ticker", ""),
            "creator": enriched_token.get("creator", ""),
            "signature": enriched_token.get("signature", ""),
            "reputation_score": reputation,
            "tags": tags,
            "external_creator_intelligence": enriched_token.get("external_creator_intelligence", {}),
            "tracker": tracker_result.get("data", {}),
        }

        self._record_metrics(summary)
        self._write_latest(summary)
        return summary

    async def run(self, events: AsyncIterable[Dict[str, Any]], max_events: Optional[int] = None) -> Dict[str, Any]:
        processed = 0
        high_reputation = 0
        async for event in events:
            result = self.process_event(event)
            if result.get("success"):
                processed += 1
                if result.get("reputation_score", 0.0) >= 0.55:
                    high_reputation += 1
            if max_events is not None and processed >= max_events:
                break
        return {
            "success": True,
            "phase": "live_prelaunch",
            "events_processed": processed,
            "high_reputation_events": high_reputation,
        }

    def _record_metrics(self, summary: Dict[str, Any]) -> None:
        recorder = getattr(self.metrics, "record_live_creator_event", None)
        if not recorder:
            return
        recorder(
            source=summary.get("source", "live_stream"),
            factory=summary.get("factory", "pump_fun"),
            mint=summary.get("mint", ""),
            symbol=summary.get("symbol", ""),
            creator=summary.get("creator", ""),
            reputation_score=summary.get("reputation_score", 0.0),
            tags=summary.get("tags", []),
        )

    def _write_latest(self, summary: Dict[str, Any]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        latest_path = self.output_dir / "latest_live_prelaunch.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)


class HeliusPumpFunWebSocketSource:
    """Helius logsSubscribe source for Pump.fun token creation events."""

    def __init__(
        self,
        ws_url: Optional[str] = None,
        api_key: Optional[str] = None,
        program_id: str = PUMPFUN_PROGRAM_ID,
        helius: Optional[HeliusProvider] = None,
        reconnect_delay_seconds: float = 5.0,
    ):
        self.api_key = api_key or os.getenv("HELIUS_API_KEY", "")
        self.ws_url = ws_url or os.getenv("HELIUS_WS_URL") or self._build_ws_url(self.api_key)
        self.program_id = program_id
        self.helius = helius or HeliusProvider(api_key=self.api_key)
        self.reconnect_delay_seconds = reconnect_delay_seconds
        self.running = False

    async def events(self) -> AsyncIterable[Dict[str, Any]]:
        self.running = True
        while self.running:
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    await websocket.send(json.dumps(self._subscription_payload()))
                    async for raw_message in websocket:
                        event = self._parse_message(raw_message)
                        if event:
                            yield event
            except asyncio.CancelledError:
                self.running = False
                raise
            except Exception as exc:
                logger.warning("Helius Pump.fun websocket error: %s", exc)
                await asyncio.sleep(self.reconnect_delay_seconds)

    def stop(self) -> None:
        self.running = False

    @staticmethod
    def _build_ws_url(api_key: str) -> str:
        if api_key:
            return f"wss://mainnet.helius-rpc.com/?api-key={api_key}"
        return "wss://api.mainnet-beta.solana.com"

    def _subscription_payload(self) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [self.program_id]},
                {"commitment": "processed"},
            ],
        }

    def _parse_message(self, raw_message: Any) -> Optional[Dict[str, Any]]:
        try:
            message = json.loads(raw_message) if isinstance(raw_message, str) else raw_message
        except (TypeError, json.JSONDecodeError):
            return None

        value = message.get("params", {}).get("result", {}).get("value", {})
        logs = value.get("logs", []) or []
        signature = value.get("signature", "")
        if not signature or not self._looks_like_token_creation(logs):
            return None

        tx_data = extract_token_creation_from_transaction(self.helius.get_transaction(signature))
        return {
            "source": "helius_websocket",
            "factory": "pump_fun",
            "program_id": self.program_id,
            "signature": signature,
            "logs": logs,
            **tx_data,
        }

    @staticmethod
    def _looks_like_token_creation(logs: List[str]) -> bool:
        creation_markers = (
            "instruction: create",
            "instruction: createmint",
            "initializemint",
            "create token",
        )
        return any(any(marker in str(log).lower() for marker in creation_markers) for log in logs)
