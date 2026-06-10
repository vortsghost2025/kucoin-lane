import os
import re
import time
from typing import Any, Dict, List, Optional

CRYPTO_PATTERNS = [
    re.compile(r"\$([A-Z]{2,10})\b"),
    re.compile(r"\b([A-Z][a-z]+[A-Z][a-z]+)\b"),
    re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}"),
    re.compile(r"https?://(?:dexscreener|geckoterminal|birdeye|jup\.ag|pump\.fun)\S+", re.IGNORECASE),
    re.compile(r"https?://t\.me/\S+", re.IGNORECASE),
]

DEFAULT_CHANNELS = [
    "pump_fun_updates",
    "solana_dex_alerts",
    "dexscreener_trending",
    "whale_alerts_sol",
    "new_token_listings",
    "raydium_listings",
]

_SESSION_DIR = os.path.join("agent-logs", "tg_sessions")


class TelegramProvider:

    def __init__(self):
        self._api_id = os.getenv("TELEGRAM_API_ID", "")
        self._api_hash = os.getenv("TELEGRAM_API_HASH", "")
        self._phone = os.getenv("TELEGRAM_PHONE", "")
        self._channels = os.getenv("TELEGRAM_CHANNELS", ",".join(DEFAULT_CHANNELS)).split(",")
        self._available = bool(self._api_id and self._api_hash)
        self._client: Any = None
        self._last_poll = 0.0

    @property
    def available(self) -> bool:
        return self._available

    def extract_signals(self, text: str) -> List[Dict[str, Any]]:
        signals = []
        for pattern in CRYPTO_PATTERNS:
            for match in pattern.finditer(text):
                signals.append({"pattern": match.group(0), "start": match.start(), "end": match.end()})
        return signals

    async def listen(self, limit: int = 50, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self._available:
            return self._offline_messages(limit, channel)
        try:
            from telethon import TelegramClient
        except ImportError:
            return self._offline_messages(limit, channel)

        if self._client is None:
            os.makedirs(_SESSION_DIR, exist_ok=True)
            session_path = os.path.join(_SESSION_DIR, "kucoin_lane")
            self._client = TelegramClient(session_path, int(self._api_id), self._api_hash)
            await self._client.start(phone=self._phone)

        channels = [channel] if channel else self._channels
        messages = []
        for ch in channels:
            try:
                async for msg in self._client.iter_messages(ch, limit=limit):
                    messages.append(self._format_message(msg, ch))
            except Exception:
                continue
        return messages

    def get_recent_messages(self, limit: int = 50, channel: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self._available:
            return self._offline_messages(limit, channel)
        return []

    @staticmethod
    def _format_message(msg: Any, channel: str) -> Dict[str, Any]:
        text = getattr(msg, "text", "") or ""
        return {
            "id": getattr(msg, "id", 0),
            "channel": channel,
            "text": text,
            "date": str(getattr(msg, "date", "")),
            "views": getattr(msg, "views", 0) or 0,
            "forwards": getattr(msg, "forwards", 0) or 0,
            "replies": getattr(msg, "reply_count", 0) or 0,
        }

    @staticmethod
    def _offline_messages(limit: int, channel: Optional[str]) -> List[Dict[str, Any]]:
        return [{
            "id": 0,
            "channel": channel or "offline",
            "text": "",
            "date": "",
            "views": 0,
            "forwards": 0,
            "replies": 0,
            "offline": True,
        }]
