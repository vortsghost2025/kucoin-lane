"""
Token data models for the KuCoin Lane pipeline.

Defines standardized dataclasses for token information flowing through
the pre-launch scanner, creator tracker, and trading decision modules.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


@dataclass
class TokenInfo:
    """Standardized token information from pre-launch scanning."""
    
    # Required fields
    mint: str
    ticker: str
    
    # Optional fields with defaults
    creator: str = ""
    community_score: float = 0.0
    pre_launch_tier: str = "unknown"
    market_cap_usd: float = 0.0
    created_at: int = 0
    social_links: Dict[str, str] = field(default_factory=dict)
    n_social_platforms: int = 0
    launch_platforms: List[str] = field(default_factory=list)
    creator_reputation: float = 0.0
    description: str = ""
    name: str = ""  # For compatibility with new_token_feed
    # Additional fields for pipeline integration
    price_usd: float = 0.0
    liquidity_usd: float = 0.0
    volume_24h_usd: float = 0.0
    source: str = "prelaunch"  # "prelaunch", "dex", "polymarket", etc.
    real_prelaunch_price_usd: Optional[float] = None  # REAL bonding curve price from Pump.fun v3
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "mint": self.mint,
            "ticker": self.ticker,
            "creator": self.creator,
            "community_score": self.community_score,
            "pre_launch_tier": self.pre_launch_tier,
            "market_cap_usd": self.market_cap_usd,
            "created_at": self.created_at,
            "social_links": self.social_links,
            "n_social_platforms": self.n_social_platforms,
            "launch_platforms": self.launch_platforms,
            "creator_reputation": self.creator_reputation,
            "description": self.description,
            "name": self.name,
            "price_usd": self.price_usd,
            "liquidity_usd": self.liquidity_usd,
            "volume_24h_usd": self.volume_24h_usd,
            "source": self.source,
            "real_prelaunch_price_usd": self.real_prelaunch_price_usd,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenInfo":
        """Create TokenInfo from dictionary (e.g., from scanner output)."""
        return cls(
            mint=data.get("mint", ""),
            ticker=data.get("ticker", ""),
            creator=data.get("creator", ""),
            community_score=float(data.get("community_score", 0.0)),
            pre_launch_tier=data.get("pre_launch_tier", "unknown"),
            market_cap_usd=float(data.get("market_cap_usd", 0.0)),
            created_at=int(data.get("created_at", 0)),
            social_links=data.get("social_links", {}),
            n_social_platforms=int(data.get("n_social_platforms", 0)),
            launch_platforms=data.get("launch_platforms", []),
            creator_reputation=float(data.get("creator_reputation", 0.0)),
            description=data.get("description", ""),
            name=data.get("name", ""),
            price_usd=float(data.get("price_usd", 0.0)),
            liquidity_usd=float(data.get("liquidity_usd", 0.0)),
            volume_24h_usd=float(data.get("volume_24h_usd", 0.0)),
            source=data.get("source", "prelaunch"),
        )
    

def dict_to_tokeninfo(data: Dict[str, Any]) -> TokenInfo:
    """Convenience function to convert scanner dict to TokenInfo."""
    return TokenInfo.from_dict(data)


def tokens_to_tokeninfo_list(tokens: List[Dict[str, Any]]) -> List[TokenInfo]:
    """Convert list of scanner token dicts to TokenInfo list."""
    return [dict_to_tokeninfo(t) for t in tokens]
