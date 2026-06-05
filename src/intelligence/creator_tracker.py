"""
Creator Tracker Agent - Creator Intelligence Module
===================================================
Monitors on-chain for new token deployments and tracks repeat creators.

Tracks:
- Deployer wallets (same wallet creates multiple tokens)
- Factory contracts (pump.fun, Moonshot, Raydium, etc.)
- Token metadata (social links, website)
- Creator reputation scores based on historical performance

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
from typing import Any, Dict, List, Optional, Set

from ..base_agent import BaseAgent, AgentStatus

logger = logging.getLogger(__name__)

DEFAULT_CREATOR_DB_PATH = "data/creator_registry.json"
DEFAULT_FACTORY_ADDRESSES = {
    "pump_fun": "6EjD2wSYh2h2cDq4sJdb1Ws0DLsrF966DyUv7nD5QB7n",
    "moonshot": "2TJC5rdL3WyvDr7Ww9YtJ3qLxQZzrqDjLPx3y0JdXvJ",
}
DEFAULT_SOLANA_RPC = "https://mainnet.helius-rpc.com/?api-key=YOUR_HELIUS_API_KEY"


@dataclass
class CreatorProfile:
    """Profile of a token creator/deployer."""
    creator_id: str  # wallet address or factory:deployer
    type: str  # "wallet" or "factory"
    display_name: str
    first_seen: str
    token_history: List[Dict[str, Any]] = field(default_factory=list)
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    social_links: Dict[str, str] = field(default_factory=dict)
    reputation_score: float = 0.0
    tags: List[str] = field(default_factory=list)


class CreatorTrackerAgent(BaseAgent):
    """
    Tracks token creators across DEX signals and on-chain deployments.
    
    Responsibilities:
    1. Maintain creator registry (wallet -> profile)
    2. Detect new tokens from known creators
    3. Score creators based on historical performance
    4. Enrich DEX signals with creator metadata
    5. Alert on alpha creator deployments
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("CreatorTrackerAgent", config)
        config = config or {}
        self.db_path = Path(config.get("creator_db_path", DEFAULT_CREATOR_DB_PATH))
        self.factory_addresses = config.get("factory_addresses", DEFAULT_FACTORY_ADDRESSES)
        self.solana_rpc_url = config.get("solana_rpc_url") or os.getenv("SOLANA_RPC_URL") or DEFAULT_SOLANA_RPC
        self.creator_profiles: Dict[str, CreatorProfile] = {}
        self._load_registry()
        
        if self.solana_rpc_url and not self.solana_rpc_url.endswith("YOUR_HELIUS_API_KEY"):
            self.logger.info(f"Solana RPC configured: {self.solana_rpc_url[:50]}...")
        else:
            self.logger.warning("No Solana RPC configured - on-chain features disabled")
    
    def _load_registry(self) -> None:
        """Load creator registry from disk."""
        if self.db_path.exists():
            try:
                with open(self.db_path) as f:
                    data = json.load(f)
                    for cid, profile in data.items():
                        self.creator_profiles[cid] = CreatorProfile(**profile)
                self.logger.info(f"Loaded {len(self.creator_profiles)} creator profiles")
            except Exception as e:
                self.logger.error(f"Failed to load creator registry: {e}")
        else:
            self.logger.info("No existing creator registry, starting fresh")
    
    def _save_registry(self) -> None:
        """Persist creator registry to disk."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        data = {cid: vars(p) for cid, p in self.creator_profiles.items()}
        with open(self.db_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point for creator detection and scoring."""
        dex_signals = input_data.get("dex_signals", [])
        new_creator_alerts = []
        
        for signal in dex_signals:
            token = signal.get("pair", "").split("/")[0]
            creator_id = signal.get("deployer", "unknown")
            
            if creator_id not in self.creator_profiles:
                profile = self._create_profile(token, signal, creator_id)
                self.creator_profiles[creator_id] = profile
                new_creator_alerts.append({
                    "token": token,
                    "creator": creator_id,
                    "signal": signal,
                })
            else:
                profile = self.creator_profiles[creator_id]
                profile.token_history.append({
                    "token": token,
                    "timestamp": signal.get("scan_time", datetime.now(timezone.utc).isoformat()),
                    "composite_score": signal.get("composite_score", 0.0),
                    "signal": signal.get("signal", "NEUTRAL"),
                })
                self._update_reputation(profile, signal)
        
        self._save_registry()
        
        return {
            "success": True,
            "data": {
                "new_creators": new_creator_alerts,
                "creator_count": len(self.creator_profiles),
            }
        }
    
    def _create_profile(self, token: str, signal: Dict, creator_id: str) -> CreatorProfile:
        """Create a new creator profile from a DEX signal."""
        return CreatorProfile(
            creator_id=creator_id,
            type="wallet",
            display_name=creator_id[:8] + "..." if len(creator_id) > 8 else creator_id,
            first_seen=signal.get("scan_time", datetime.now(timezone.utc).isoformat()),
            token_history=[{
                "token": token,
                "timestamp": signal.get("scan_time"),
                "composite_score": signal.get("composite_score", 0.0),
                "signal": signal.get("signal", "NEUTRAL"),
            }],
            performance_metrics={"avg_score": signal.get("composite_score", 0.0)},
            reputation_score=0.1,
        )
    
    def _update_reputation(self, profile: CreatorProfile, signal: Dict) -> None:
        """Update creator reputation based on new signal performance."""
        score = signal.get("composite_score", 0.0)
        history = profile.token_history
        
        scores = [t.get("composite_score", 0.0) for t in history]
        profile.performance_metrics["avg_score"] = sum(scores) / len(scores) if scores else 0.0
        profile.performance_metrics["total_tokens"] = len(history)
        
        profile.reputation_score = profile.performance_metrics["avg_score"] * math.sqrt(len(history))
        
        if profile.reputation_score > 0.8:
            profile.tags.append("alpha")
    
    def _rpc_call(self, method: str, params: List[Any] = None) -> Optional[Dict[str, Any]]:
        """Make a JSON-RPC call to Solana RPC."""
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
        """Fetch token metadata from Solana blockchain."""
        result = self._rpc_call("getTokenSupply", [mint])
        return result
    
    def get_wallet_tokens(self, wallet: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all tokens held by a wallet via SPL token program."""
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
        """Get transaction signatures for a Solana address (wallet or program)."""
        result = self._rpc_call("getSignaturesForAddress", [address, {"limit": limit}])
        return result or []
    
    def check_creator_deployments(self, creator_wallet: str, since: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Check if a creator wallet has deployed new tokens recently.
        
        Returns list of recent token deployments with metadata.
        """
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
        """Return list of high-reputation creators."""
        return [p for p in self.creator_profiles.values() if p.reputation_score >= min_score]
    
    def get_signals_for_token(self, token: str) -> List[Dict]:
        """Get all signals for a specific token."""
        return [s for s in self.dex_signals if s.get("pair", "").startswith(token)]