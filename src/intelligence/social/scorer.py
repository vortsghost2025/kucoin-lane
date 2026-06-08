import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

SIGNAL_WEIGHTS: Dict[str, float] = {
    "PUMP_HYPE": 0.15,
    "CEX_LISTING_RUMOR": 0.30,
    "WHALE_ACTIVITY": 0.20,
    "NEW_COIN_ANNOUNCEMENT": 0.10,
    "PUMP_GRADUATION": 0.15,
    "AIRDROP_ALERT": 0.05,
    "DANGER_WARNING": -0.25,
}

SENTIMENT_MAP: Dict[str, float] = {
    "very_bullish": 1.0,
    "bullish": 0.6,
    "neutral": 0.0,
    "bearish": -0.6,
    "very_bearish": -1.0,
}

VOLUME_MAP: Dict[str, float] = {
    "high": 1.0,
    "medium": 0.5,
    "low": 0.2,
}

_PUMP_ADDRESS_RE = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")
_DEX_LINK_RE = re.compile(r"https?://(?:dexscreener\.com|geckoterminal\.com|birdeye\.so|jup\.ag)/\S+", re.IGNORECASE)
_CONTRACT_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")


@dataclass
class SocialScore:
    composite: float = 0.0
    signal_score: float = 0.0
    engagement: float = 0.0
    has_dex_link: bool = False
    has_contract: bool = False
    signals: List[str] = field(default_factory=list)
    sentiment: str = "neutral"
    volume: str = "low"
    alert_level: str = "NEUTRAL"


class SocialSignalScorer:

    def __init__(self):
        self._weights = SIGNAL_WEIGHTS
        self._sentiment = SENTIMENT_MAP
        self._volume = VOLUME_MAP

    def score_telegram_message(self, text: str, views: int = 0, forwards: int = 0, replies: int = 0) -> SocialScore:
        signals = self._detect_signals(text)
        sentiment = self._detect_sentiment(text)
        volume = self._detect_volume(views, forwards, replies)
        has_dex = bool(_DEX_LINK_RE.search(text))
        has_contract = bool(_CONTRACT_RE.search(text))

        signal_score = self._compute_signal_score(signals)
        engagement = self._compute_engagement(views, forwards, replies)

        composite = (
            signal_score * 0.6
            + engagement * 0.25
            + (0.1 if has_dex else 0.0)
            + (0.1 if has_contract else 0.0)
        )
        composite = max(-1.0, min(1.0, composite))

        if "DANGER_WARNING" in signals:
            composite = min(composite, -0.1)

        alert_level = self._classify_alert(composite)

        return SocialScore(
            composite=composite,
            signal_score=signal_score,
            engagement=engagement,
            has_dex_link=has_dex,
            has_contract=has_contract,
            signals=signals,
            sentiment=sentiment,
            volume=volume,
            alert_level=alert_level,
        )

    def _detect_signals(self, text: str) -> List[str]:
        t = text.lower()
        found = []
        if any(kw in t for kw in ("pump", "moon", "rocket", "🚀", "to the moon", "send it")):
            found.append("PUMP_HYPE")
        if any(kw in t for kw in ("listing", "binance", "kucoin", "coinbase", "cex", "exchange listing")):
            found.append("CEX_LISTING_RUMOR")
        if any(kw in t for kw in ("whale", "big buy", "accumulation", "wallet", "smart money")):
            found.append("WHALE_ACTIVITY")
        if any(kw in t for kw in ("launch", "new token", "just launched", "fair launch", "presale")):
            found.append("NEW_COIN_ANNOUNCEMENT")
        if any(kw in t for kw in ("graduated", "raydium", "graduation", "bonding curve")):
            found.append("PUMP_GRADUATION")
        if any(kw in t for kw in ("airdrop", "claim", "free token", "reward")):
            found.append("AIRDROP_ALERT")
        if any(kw in t for kw in ("rug", "scam", "honeypot", "danger", "avoid", "red flag", "do not buy")):
            found.append("DANGER_WARNING")
        return found or ["NEUTRAL"]

    def _detect_sentiment(self, text: str) -> str:
        t = text.lower()
        bullish_kw = ("buy", "long", "bullish", "moon", "pump", "gem", "alpha", "early")
        bearish_kw = ("sell", "short", "bearish", "dump", "rug", "scam", "avoid", "dead")
        b = sum(1 for kw in bullish_kw if kw in t)
        s = sum(1 for kw in bearish_kw if kw in t)
        if s > b + 1:
            return "very_bearish" if s > b + 2 else "bearish"
        if b > s + 1:
            return "very_bullish" if b > s + 2 else "bullish"
        return "neutral"

    def _detect_volume(self, views: int, forwards: int, replies: int) -> str:
        score = views * 0.001 + forwards * 0.5 + replies * 1.0
        if score >= 50:
            return "high"
        if score >= 10:
            return "medium"
        return "low"

    def _compute_signal_score(self, signals: List[str]) -> float:
        total = 0.0
        for sig in signals:
            total += self._weights.get(sig, 0.0)
        return max(-1.0, min(1.0, total))

    def _compute_engagement(self, views: int, forwards: int, replies: int) -> float:
        score = views * 0.0001 + forwards * 0.1 + replies * 0.2
        return min(1.0, score)

    @staticmethod
    def _classify_alert(composite: float) -> str:
        if composite >= 0.5:
            return "STRONG_BULLISH"
        if composite >= 0.2:
            return "BULLISH"
        if composite >= -0.2:
            return "NEUTRAL"
        if composite >= -0.5:
            return "BEARISH"
        return "STRONG_BEARISH"
