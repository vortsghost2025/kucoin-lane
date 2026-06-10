"""
Creator Tracker Agent - Creator Intelligence Module
===================================================
Monitors on-chain for new token deployments and tracks repeat creators.

Tracks:
- Deployer wallets (same wallet creates multiple tokens)
- Factory contracts (pump.fun, Moonshot, Raydium, etc.)
- Token metadata (social links, website)
- Creator reputation scores based on historical performance
- Launch pattern analytics (time-of-day, day-of-week, factory preference)
- Safety signal integration (rug history, mint/freeze authority)
- Social signal integration (community size, engagement, sentiment)

Signals:
- NEW_CREATOR: Unknown deployer with high-composite DEX signal
- REPEAT_CREATOR: Known high-performing creator deployed new token
- ALPHA_Creator: Top-tier creator (top 10% by performance) deployed new token
"""

import json
import logging
import math
import os
import requests
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..base_agent import BaseAgent, AgentStatus
from .chain.prelaunch_scanner import PreLaunchScanner, extract_social_links, compute_community_score, classify_pre_launch
from .chain.safety_guard import SafetyGuard, RISK_TIERS
from .chain.helius_provider import HeliusProvider
from .social.scorer import SocialSignalScorer, SocialScore

logger = logging.getLogger(__name__)

DEFAULT_CREATOR_DB_PATH = "data/creator_registry.json"
DEFAULT_FACTORY_ADDRESSES = {
    "pump_fun": "6EjD2wSYh2h2cDq4sJdb1Ws0DLsrF966DyUv7nD5QB7n",
    "moonshot": "2TJC5rdL3WyvDr7Ww9YtJ3qLxQZzrqDjLPx3y0JdXvJ",
}
DEFAULT_SOLANA_RPC = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

LAUNCH_HOUR_BUCKETS = {
    "us_peak": range(13, 22),
    "eu_peak": range(8, 16),
    "asia_peak": range(0, 8),
    "off_peak": range(22, 24),
}

DAY_OF_WEEK_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

REPUTATION_COMPONENTS = {
    "base_performance": 0.30,
    "safety_modifier": 0.25,
    "social_modifier": 0.20,
    "pattern_consistency": 0.15,
    "graduation_rate": 0.10,
}


@dataclass
class LaunchPattern:
    hour_histogram: Dict[int, int] = field(default_factory=dict)
    day_histogram: Dict[str, int] = field(default_factory=dict)
    factory_preference: Dict[str, int] = field(default_factory=dict)
    avg_time_between_launches_hr: float = 0.0
    typical_launch_bucket: str = "unknown"


@dataclass
class CreatorProfile:
    """Profile of a token creator/deployer."""
    creator_id: str
    type: str
    display_name: str
    first_seen: str
    token_history: List[Dict[str, Any]] = field(default_factory=list)
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    social_links: Dict[str, str] = field(default_factory=dict)
    reputation_score: float = 0.0
    tags: List[str] = field(default_factory=list)
    launch_pattern: Dict[str, Any] = field(default_factory=dict)
    safety_summary: Dict[str, Any] = field(default_factory=dict)
    social_summary: Dict[str, Any] = field(default_factory=dict)


def _compute_launch_pattern(token_history: List[Dict]) -> LaunchPattern:
    hour_hist: Dict[int, int] = {}
    day_hist: Dict[str, int] = {}
    factory_pref: Dict[str, int] = {}

    timestamps = []
    for entry in token_history:
        ts_str = entry.get("timestamp", "")
        factory = entry.get("factory", "unknown")
        factory_pref[factory] = factory_pref.get(factory, 0) + 1

        if not ts_str:
            continue
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        hour = dt.hour
        hour_hist[hour] = hour_hist.get(hour, 0) + 1
        day_name = DAY_OF_WEEK_NAMES[dt.weekday()]
        day_hist[day_name] = day_hist.get(day_name, 0) + 1
        timestamps.append(dt)

    avg_gap_hr = 0.0
    if len(timestamps) >= 2:
        sorted_ts = sorted(timestamps)
        gaps = [(sorted_ts[i + 1] - sorted_ts[i]).total_seconds() / 3600.0 for i in range(len(sorted_ts) - 1)]
        avg_gap_hr = sum(gaps) / len(gaps) if gaps else 0.0

    typical_bucket = "unknown"
    if hour_hist:
        dominant_hour = max(hour_hist, key=hour_hist.get)
        for bucket, hours in LAUNCH_HOUR_BUCKETS.items():
            if dominant_hour in hours:
                typical_bucket = bucket
                break

    return LaunchPattern(
        hour_histogram=hour_hist,
        day_histogram=day_hist,
        factory_preference=factory_pref,
        avg_time_between_launches_hr=round(avg_gap_hr, 2),
        typical_launch_bucket=typical_bucket,
    )


def _compute_safety_modifier(safety_checks: List[Dict]) -> float:
    if not safety_checks:
        return 0.0
    total = 0.0
    for check in safety_checks:
        risk_level = check.get("risk_level", 3)
        if risk_level <= 1:
            total += 0.25
        elif risk_level == 2:
            total += 0.0
        elif risk_level == 3:
            total -= 0.15
        else:
            total -= 0.35
    return max(-1.0, min(1.0, total / len(safety_checks)))


def _compute_social_modifier(social_scores: List[Dict]) -> float:
    if not social_scores:
        return 0.0
    composites = [s.get("composite", 0.0) for s in social_scores if "composite" in s]
    if not composites:
        return 0.0
    return max(-1.0, min(1.0, sum(composites) / len(composites)))


class CreatorTrackerAgent(BaseAgent):
    """
    Tracks token creators across DEX signals and on-chain deployments.

    Responsibilities:
    1. Maintain creator registry (wallet -> profile)
    2. Detect new tokens from known creators
    3. Score creators based on historical performance
    4. Enrich DEX signals with creator metadata
    5. Alert on alpha creator deployments
    6. Integrate PreLaunchScanner for social link discovery
    7. Integrate SafetyGuard for risk-aware reputation scoring
    8. Track launch patterns (time, day, factory preference)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("CreatorTrackerAgent", config)
        config = config or {}
        self.db_path = Path(config.get("creator_db_path", DEFAULT_CREATOR_DB_PATH))
        self.factory_addresses = config.get("factory_addresses", DEFAULT_FACTORY_ADDRESSES)
        self.solana_rpc_url = config.get("solana_rpc_url") or os.getenv("SOLANA_RPC_URL") or DEFAULT_SOLANA_RPC
        self.creator_profiles: Dict[str, CreatorProfile] = {}
        self.dex_signals: List[Dict] = []
        self._load_registry()

        self.prelaunch_scanner = PreLaunchScanner(rpc_url=self.solana_rpc_url)
        self.safety_guard = SafetyGuard(rpc_url=self.solana_rpc_url)
        self.social_scorer = SocialSignalScorer()
        self.helius = HeliusProvider()

        if self.solana_rpc_url and not self.solana_rpc_url.endswith("YOUR_HELIUS_API_KEY"):
            self.logger.info(f"Solana RPC configured: {self.solana_rpc_url[:50]}...")
        else:
            self.logger.warning("No Solana RPC configured - on-chain features disabled")

    def _load_registry(self) -> None:
        if self.db_path.exists():
            try:
                with open(self.db_path) as f:
                    data = json.load(f)
                # Defensive: ensure registry is a dict (could be corrupted list)
                if not isinstance(data, dict):
                    self.logger.error(f"Creator registry is not a dict (type: {type(data).__name__}), starting fresh")
                    return
                for cid, profile in data.items():
                    self.creator_profiles[cid] = CreatorProfile(**profile)
                self.logger.info(f"Loaded {len(self.creator_profiles)} creator profiles")
            except Exception as e:
                self.logger.error(f"Failed to load creator registry: {e}")
        else:
            self.logger.info("No existing creator registry, starting fresh")

    def _save_registry(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for cid, p in self.creator_profiles.items():
            d = vars(p).copy()
            d["launch_pattern"] = vars(p.launch_pattern) if isinstance(p.launch_pattern, LaunchPattern) else p.launch_pattern
            data[cid] = d
        with open(self.db_path, "w") as f:
            json.dump(data, f, indent=2)

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point for creator detection and scoring."""
        dex_signals = input_data.get("dex_signals", [])
        pumpfun_tokens = input_data.get("pumpfun_tokens", [])
        new_creator_alerts = []
        updated_profiles = []

        for signal in dex_signals:
            token = signal.get("pair", "").split("/")[0]
            creator_id = signal.get("deployer", "unknown")
            factory = self._detect_factory(signal)

            if creator_id not in self.creator_profiles:
                profile = self._create_profile(token, signal, creator_id, factory)
                self.creator_profiles[creator_id] = profile
                new_creator_alerts.append({
                    "token": token,
                    "creator": creator_id,
                    "signal": signal,
                    "factory": factory,
                })
            else:
                profile = self.creator_profiles[creator_id]
                profile.token_history.append({
                    "token": token,
                    "timestamp": signal.get("scan_time", datetime.now(timezone.utc).isoformat()),
                    "composite_score": signal.get("composite_score", 0.0),
                    "signal": signal.get("signal", "NEUTRAL"),
                    "factory": factory,
                })

            self._enrich_social_links(profile, signal)
            self._run_safety_check(profile, signal)
            self._update_reputation(profile, signal)
            updated_profiles.append(creator_id)

        for token_data in pumpfun_tokens:
            creator_id = token_data.get("creator", "unknown")
            
            # Resolve unknown creator via Helius
            if (not creator_id or creator_id == "unknown") and token_data.get("mint"):
                mint = token_data["mint"]
                resolved = self.helius.get_mint_creator(mint)
                if resolved:
                    creator_id = resolved
                    token_data["creator"] = creator_id
                    self.logger.info(f"Resolved creator for {mint[:8]}...: {creator_id}")
            
            if not creator_id or creator_id == "unknown":
                continue

            if creator_id not in self.creator_profiles:
                factory = token_data.get("factory", "pump_fun")
                profile = self._create_profile_from_pumpfun(token_data, creator_id, factory)
                self.creator_profiles[creator_id] = profile
                new_creator_alerts.append({
                    "token": token_data.get("ticker", ""),
                    "creator": creator_id,
                    "signal": {"source": "pumpfun", "community_score": token_data.get("community_score", 0.0)},
                    "factory": factory,
                })
            else:
                profile = self.creator_profiles[creator_id]
                profile.token_history.append({
                    "token": token_data.get("ticker", ""),
                    "timestamp": token_data.get("created_at", datetime.now(timezone.utc).isoformat()),
                    "composite_score": token_data.get("community_score", 0.0),
                    "signal": "PUMPFUN_NEW",
                    "factory": token_data.get("factory", "pump_fun"),
                })

            self._enrich_social_links_from_pumpfun(profile, token_data)
            self._run_safety_check_from_pumpfun(profile, token_data)
            self._update_reputation(profile, token_data)
            if creator_id not in updated_profiles:
                updated_profiles.append(creator_id)

        for cid in updated_profiles:
            profile = self.creator_profiles[cid]
            pattern = _compute_launch_pattern(profile.token_history)
            profile.launch_pattern = vars(pattern)
            self._apply_pattern_consistency(profile, pattern)

        self._save_registry()

        alpha_creators = self.get_alpha_creators()
        return {
            "success": True,
            "data": {
                "new_creators": new_creator_alerts,
                "creator_count": len(self.creator_profiles),
                "alpha_count": len(alpha_creators),
                "updated_profiles": updated_profiles,
            }
        }

    def _detect_factory(self, signal: Dict) -> str:
        program_id = signal.get("program_id", "")
        for name, addr in self.factory_addresses.items():
            if program_id == addr:
                return name
        dex = signal.get("dex_id", signal.get("dex", "")).lower()
        if "pump" in dex:
            return "pump_fun"
        if "raydium" in dex:
            return "raydium"
        return "unknown"

    def _create_profile(self, token: str, signal: Dict, creator_id: str, factory: str = "unknown") -> CreatorProfile:
        social_links = self._extract_social_links_from_signal(signal)
        return CreatorProfile(
            creator_id=creator_id,
            type="wallet",
            display_name=creator_id[:8] + "..." if len(creator_id) > 8 else creator_id,
            first_seen=signal.get("scan_time", datetime.now(timezone.utc).isoformat()),
            token_history=[{
                "token": token,
                "timestamp": signal.get("scan_time", datetime.now(timezone.utc).isoformat()),
                "composite_score": signal.get("composite_score", 0.0),
                "signal": signal.get("signal", "NEUTRAL"),
                "factory": factory,
            }],
            performance_metrics={"avg_score": signal.get("composite_score", 0.0)},
            social_links=social_links,
            reputation_score=0.1,
        )

    def _create_profile_from_pumpfun(self, token_data: Dict, creator_id: str, factory: str = "pump_fun") -> CreatorProfile:
        pf_social = token_data.get("social_links", {})
        flat_social = {}
        for platform, handles in pf_social.items():
            if isinstance(handles, list) and handles:
                flat_social[platform] = handles[0]
            elif isinstance(handles, str):
                flat_social[platform] = handles

        community_score = token_data.get("community_score", 0.0)
        pre_launch_tier = token_data.get("pre_launch_tier", "NOISE")

        return CreatorProfile(
            creator_id=creator_id,
            type="wallet",
            display_name=creator_id[:8] + "..." if len(creator_id) > 8 else creator_id,
            first_seen=token_data.get("created_at", datetime.now(timezone.utc).isoformat()),
            token_history=[{
                "token": token_data.get("ticker", ""),
                "timestamp": token_data.get("created_at", datetime.now(timezone.utc).isoformat()),
                "composite_score": community_score,
                "signal": "PUMPFUN_NEW",
                "factory": factory,
            }],
            performance_metrics={"avg_score": community_score, "pre_launch_tier": pre_launch_tier},
            social_links=flat_social,
            reputation_score=min(1.0, community_score * 0.3),
        )

    def _extract_social_links_from_signal(self, signal: Dict) -> Dict[str, str]:
        links = {}
        for field_name in ("description", "website", "telegram", "twitter"):
            text = signal.get(field_name, "")
            if not text:
                continue
            extracted = extract_social_links(str(text))
            for platform, handles in extracted.items():
                if handles and platform not in links:
                    links[platform] = handles[0]
        if signal.get("telegram") and "telegram" not in links:
            val = str(signal["telegram"])
            if not val.startswith("http"):
                links["telegram"] = val
        if signal.get("twitter") and "twitter" not in links:
            val = str(signal["twitter"])
            if not val.startswith("http"):
                links["twitter"] = val
        return links

    def _enrich_social_links(self, profile: CreatorProfile, signal: Dict) -> None:
        new_links = self._extract_social_links_from_signal(signal)
        for platform, handle in new_links.items():
            if platform not in profile.social_links:
                profile.social_links[platform] = handle
                self.logger.debug(f"Added {platform} link to {profile.creator_id}: {handle}")

        mint = signal.get("mint", signal.get("address", ""))
        if mint and len(mint) > 30:
            try:
                pf_data = self.prelaunch_scanner.get_token_social_links(mint)
                pf_links = pf_data.get("social_links", {})
                for platform, handles in pf_links.items():
                    if isinstance(handles, list) and handles:
                        if platform not in profile.social_links:
                            profile.social_links[platform] = handles[0]
                    elif isinstance(handles, str) and platform not in profile.social_links:
                        profile.social_links[platform] = handles
            except Exception as e:
                self.logger.debug(f"PreLaunch social enrichment failed for {mint}: {e}")

    def _enrich_social_links_from_pumpfun(self, profile: CreatorProfile, token_data: Dict) -> None:
        pf_social = token_data.get("social_links", {})
        for platform, handles in pf_social.items():
            if platform not in profile.social_links:
                if isinstance(handles, list) and handles:
                    profile.social_links[platform] = handles[0]
                elif isinstance(handles, str):
                    profile.social_links[platform] = handles

    def _run_safety_check(self, profile: CreatorProfile, signal: Dict) -> None:
        mint = signal.get("mint", signal.get("address", ""))
        if not mint or len(mint) < 30:
            return

        try:
            result = self.safety_guard.check_token(
                mint=mint,
                token_name=signal.get("pair", "").split("/")[0],
                extra={
                    "social_links": profile.social_links,
                    "creator_graduated_count": profile.performance_metrics.get("graduated_count", 0),
                    "creator_failed_count": profile.performance_metrics.get("failed_count", 0),
                },
            )

            if "safety_checks" not in profile.safety_summary:
                profile.safety_summary["safety_checks"] = []
            profile.safety_summary["safety_checks"].append({
                "mint": mint,
                "risk_tier": result.get("risk_tier", "UNKNOWN"),
                "risk_score": result.get("risk_score", 0.5),
                "risk_level": result.get("risk_level", 3),
                "tradeable": result.get("tradeable", False),
                "red_flags": result.get("red_flags", []),
                "safe_signals": result.get("safe_signals", []),
                "timestamp": result.get("timestamp", ""),
            })

            latest_risk = result.get("risk_tier", "MODERATE_RISK")
            profile.safety_summary["latest_risk_tier"] = latest_risk
            profile.safety_summary["latest_risk_score"] = result.get("risk_score", 0.5)
            profile.safety_summary["tradeable"] = result.get("tradeable", False)
            profile.safety_summary["avoid"] = result.get("avoid", False)

        except Exception as e:
            self.logger.warning(f"Safety check failed for {mint}: {e}")

    def _run_safety_check_from_pumpfun(self, profile: CreatorProfile, token_data: Dict) -> None:
        mint = token_data.get("mint", "")
        if not mint or len(mint) < 30:
            return

        try:
            result = self.safety_guard.check_token(
                mint=mint,
                token_name=token_data.get("name", token_data.get("ticker", "")),
                extra={
                    "social_links": profile.social_links,
                    "graduated": token_data.get("graduated", False),
                    "creator_graduated_count": profile.performance_metrics.get("graduated_count", 0),
                    "creator_failed_count": profile.performance_metrics.get("failed_count", 0),
                    "telegram_members": token_data.get("telegram_members", 0),
                },
            )

            if "safety_checks" not in profile.safety_summary:
                profile.safety_summary["safety_checks"] = []
            profile.safety_summary["safety_checks"].append({
                "mint": mint,
                "risk_tier": result.get("risk_tier", "UNKNOWN"),
                "risk_score": result.get("risk_score", 0.5),
                "risk_level": result.get("risk_level", 3),
                "tradeable": result.get("tradeable", False),
                "red_flags": result.get("red_flags", []),
                "safe_signals": result.get("safe_signals", []),
                "timestamp": result.get("timestamp", ""),
            })

            profile.safety_summary["latest_risk_tier"] = result.get("risk_tier", "MODERATE_RISK")
            profile.safety_summary["latest_risk_score"] = result.get("risk_score", 0.5)
            profile.safety_summary["tradeable"] = result.get("tradeable", False)
            profile.safety_summary["avoid"] = result.get("avoid", False)

        except Exception as e:
            self.logger.warning(f"Safety check failed for pumpfun token {mint}: {e}")

    def _update_reputation(self, profile: CreatorProfile, signal_or_token: Dict) -> None:
        history = profile.token_history

        # Compute basic performance metrics
        scores = [t.get("composite_score", 0.0) for t in history]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        profile.performance_metrics["avg_score"] = round(avg_score, 4)
        profile.performance_metrics["total_tokens"] = len(history)

        graduated = sum(1 for t in history if t.get("graduated", False))
        profile.performance_metrics["graduated_count"] = graduated
        profile.performance_metrics["failed_count"] = len(history) - graduated
        if len(history) > 0:
            profile.performance_metrics["graduation_rate"] = round(graduated / len(history), 4)

        # Reputation calculation:
        # - For a creator with a single token, keep the initial reputation (e.g., 0.1).
        # - For creators with multiple tokens, use avg_score weighted by sqrt of history length.
        if len(history) > 1:
            # Scale reputation by average composite score and history size
            reputation = avg_score * math.sqrt(len(history))
            profile.reputation_score = round(reputation, 4)
        else:
            # Preserve existing reputation (set during profile creation)
            profile.reputation_score = round(profile.reputation_score, 4)

        # Retain existing tag logic based on new reputation score
        profile.tags = [t for t in profile.tags if t not in ("alpha", "repeat", "risky", "high_frequency", "serial_launcher")]
        if profile.reputation_score > 0.8:
            profile.tags.append("alpha")
        elif profile.reputation_score > 0.5:
            profile.tags.append("repeat")
        if profile.safety_summary.get("avoid"):
            profile.tags.append("risky")
        if len(history) >= 5:
            profile.tags.append("high_frequency")
        if len(history) >= 10:
            profile.tags.append("serial_launcher")

        n_social = len(profile.social_links)
        profile.performance_metrics["n_social_platforms"] = n_social

        profile.tags = [t for t in profile.tags if t not in ("alpha", "repeat", "risky", "high_frequency", "serial_launcher")]
        if profile.reputation_score > 0.8:
            profile.tags.append("alpha")
        elif profile.reputation_score > 0.5:
            profile.tags.append("repeat")
        if profile.safety_summary.get("avoid"):
            profile.tags.append("risky")
        if len(history) >= 5:
            profile.tags.append("high_frequency")
        if len(history) >= 10:
            profile.tags.append("serial_launcher")

        n_social = len(profile.social_links)
        profile.performance_metrics["n_social_platforms"] = n_social

    def _apply_pattern_consistency(self, profile: CreatorProfile, pattern: LaunchPattern) -> None:
        n_tokens = len(profile.token_history)
        if n_tokens < 2:
            profile.performance_metrics["pattern_consistency"] = 0.0
            return

        n_factories = len(pattern.factory_preference)
        if n_factories == 1 and n_tokens >= 3:
            factory_consistency = 0.5
        elif n_factories == 1:
            factory_consistency = 0.3
        else:
            factory_consistency = 0.0

        n_hours = len(pattern.hour_histogram)
        if n_hours <= 2 and n_tokens >= 3:
            time_consistency = 0.3
        elif n_hours <= 4:
            time_consistency = 0.1
        else:
            time_consistency = 0.0

        profile.performance_metrics["pattern_consistency"] = round(
            max(0.0, min(1.0, factory_consistency + time_consistency)), 4
        )

    def scan_pumpfun_creators(self, limit: int = 50) -> Dict[str, Any]:
        """Scan pump.fun for new tokens and enrich creator profiles."""
        tokens = self.prelaunch_scanner.scan_pumpfun_new(limit=limit)
        if not tokens:
            return {"scanned": 0, "new_creators": [], "updated": []}

        result = self.execute({"pumpfun_tokens": tokens})

        communities = self.prelaunch_scanner.discover_launch_communities(tokens)

        return {
            "scanned": len(tokens),
            "new_creators": result["data"]["new_creators"],
            "updated_profiles": result["data"]["updated_profiles"],
            "high_confidence": communities.get("high_confidence_tokens", 0),
            "recommended_tg": communities.get("recommended_monitoring", []),
        }

    def scan_pumpfun_callouts(self, limit: int = 30) -> Dict[str, Any]:
        """Scan pump.fun callouts section for upcoming launches."""
        tokens = self.prelaunch_scanner.scan_pumpfun_callouts(limit=limit)
        if not tokens:
            return {"scanned": 0, "new_creators": [], "updated": []}

        result = self.execute({"pumpfun_tokens": tokens})

        return {
            "scanned": len(tokens),
            "new_creators": result["data"]["new_creators"],
            "updated_profiles": result["data"]["updated_profiles"],
        }

    def score_social_signals(self, creator_id: str, messages: List[Dict]) -> SocialScore:
        """Score social signals for a creator's community messages."""
        if creator_id not in self.creator_profiles:
            return SocialScore()

        profile = self.creator_profiles[creator_id]
        if "social_scores" not in profile.social_summary:
            profile.social_summary["social_scores"] = []

        best = SocialScore()
        for msg in messages:
            text = msg.get("text", "")
            views = msg.get("views", 0)
            forwards = msg.get("forwards", 0)
            replies = msg.get("replies", 0)

            score = self.social_scorer.score_telegram_message(text, views, forwards, replies)
            profile.social_summary["social_scores"].append({
                "composite": score.composite,
                "signal_score": score.signal_score,
                "engagement": score.engagement,
                "signals": score.signals,
                "sentiment": score.sentiment,
                "alert_level": score.alert_level,
                "timestamp": msg.get("date", ""),
            })

            if score.composite > best.composite:
                best = score

        profile.social_summary["best_alert_level"] = best.alert_level
        profile.social_summary["best_composite"] = best.composite
        self._update_reputation(profile, {})

        return best

    def _rpc_call(self, method: str, params: List[Any] = None) -> Optional[Dict[str, Any]]:
        if not self.solana_rpc_url or "YOUR_HELIUS_API_KEY" in self.solana_rpc_url:
            return None
        try:
            resp = requests.post(
                self.solana_rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []},
                timeout=10,
            )
            data = resp.json()
            return data.get("result")
        except Exception as e:
            self.logger.warning(f"RPC call {method} failed: {e}")
            return None

    def get_token_metadata(self, mint: str) -> Optional[Dict[str, Any]]:
        result = self._rpc_call("getTokenSupply", [mint])
        return result

    def get_wallet_tokens(self, wallet: str, limit: int = 100) -> List[Dict[str, Any]]:
        result = self._rpc_call("getTokenAccountsByOwner", [
            wallet,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"},
        ])
        if not result:
            return []
        accounts = result.get("value", [])
        return [
            {
                "mint": acc["account"]["data"]["parsed"]["info"]["mint"],
                "amount": acc["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"],
                "decimals": acc["account"]["data"]["parsed"]["info"]["tokenAmount"]["decimals"],
            }
            for acc in accounts
        ]

    def get_signatures_for_address(self, address: str, limit: int = 50) -> List[Dict[str, Any]]:
        result = self._rpc_call("getSignaturesForAddress", [address, {"limit": limit}])
        return result or []

    def check_creator_deployments(self, creator_wallet: str, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        if not self.solana_rpc_url or "YOUR_HELIUS_API_KEY" in self.solana_rpc_url:
            return []

        signatures = self.get_signatures_for_address(creator_wallet, limit=100)
        if not signatures:
            return []

        deployments = []
        for sig in signatures:
            sig_time = datetime.fromtimestamp(sig.get("blockTime", 0), tz=timezone.utc)
            if since and sig_time < since:
                break

            tx_hash = sig.get("signature", "")
            if tx_hash:
                deployments.append({
                    "signature": tx_hash,
                    "timestamp": sig_time.isoformat(),
                    "slot": sig.get("slot"),
                    "err": sig.get("err"),
                })

        return deployments

    def get_alpha_creators(self, min_score: float = 0.5) -> List[CreatorProfile]:
        return [p for p in self.creator_profiles.values() if p.reputation_score >= min_score]

    def get_safe_creators(self, max_risk_level: int = 1) -> List[CreatorProfile]:
        return [
            p for p in self.creator_profiles.values()
            if RISK_TIERS.get(p.safety_summary.get("latest_risk_tier", "MODERATE_RISK"), {}).get("level", 3) <= max_risk_level
        ]

    def get_creators_by_pattern(self, bucket: str, min_tokens: int = 3) -> List[CreatorProfile]:
        return [
            p for p in self.creator_profiles.values()
            if p.launch_pattern.get("typical_launch_bucket") == bucket
            and len(p.token_history) >= min_tokens
        ]

    def get_creator_detail(self, creator_id: str) -> Optional[Dict[str, Any]]:
        if creator_id not in self.creator_profiles:
            return None
        p = self.creator_profiles[creator_id]
        return {
            "creator_id": p.creator_id,
            "display_name": p.display_name,
            "type": p.type,
            "first_seen": p.first_seen,
            "total_tokens": len(p.token_history),
            "reputation_score": p.reputation_score,
            "tags": p.tags,
            "social_links": p.social_links,
            "performance_metrics": p.performance_metrics,
            "launch_pattern": p.launch_pattern,
            "safety_summary": {
                k: v for k, v in p.safety_summary.items()
                if k != "safety_checks"
            },
            "safety_check_count": len(p.safety_summary.get("safety_checks", [])),
            "social_summary": {
                k: v for k, v in p.social_summary.items()
                if k != "social_scores"
            },
            "social_score_count": len(p.social_summary.get("social_scores", [])),
            "latest_tokens": p.token_history[-5:] if p.token_history else [],
        }

    def get_signals_for_token(self, token: str) -> List[Dict]:
        return [s for s in self.dex_signals if s.get("pair", "").startswith(token)]
