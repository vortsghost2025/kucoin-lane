import json
import os
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

_XAI_BASE = "https://api.x.ai/v1"
_MIN_INTERVAL = 2.0


class XAIProvider:

    def __init__(self):
        self._api_key = os.getenv("XAI_API_KEY", "")
        self._model = os.getenv("XAI_MODEL", "grok-3-mini")
        self._available = bool(self._api_key)
        self._last_call = 0.0

    @property
    def available(self) -> bool:
        return self._available

    def analyze_social_post(self, text: str, context: str = "") -> Dict[str, Any]:
        if not self._available:
            return self._fallback(text)
        prompt = (
            "Analyze this crypto social media post. Return JSON with keys: "
            "signals (list of signal types), sentiment (very_bullish/bullish/neutral/bearish/very_bearish), "
            "volume (high/medium/low), tokens_mentioned (list), summary (string).\n"
            f"Context: {context}\nPost: {text}"
        )
        resp = self._call(prompt)
        if resp:
            return self._parse(resp)
        return self._fallback(text)

    def analyze_telegram_batch(self, messages: List[str], context: str = "") -> List[Dict[str, Any]]:
        return [self.analyze_social_post(m, context) for m in messages]

    def _call(self, prompt: str) -> Optional[str]:
        self._rate_limit()
        url = f"{_XAI_BASE}/chat/completions"
        body = json.dumps({
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 512,
        }).encode()
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(5)
                return self._call(prompt)
            return None
        except Exception:
            return None

    def _rate_limit(self):
        now = time.monotonic()
        gap = now - self._last_call
        if gap < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - gap)
        self._last_call = time.monotonic()

    @staticmethod
    def _parse(raw: str) -> Dict[str, Any]:
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            return json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            return {"raw": raw, "signals": [], "sentiment": "neutral", "volume": "low", "tokens_mentioned": [], "summary": raw[:200]}

    @staticmethod
    def _fallback(text: str) -> Dict[str, Any]:
        return {
            "signals": [],
            "sentiment": "neutral",
            "volume": "low",
            "tokens_mentioned": [],
            "summary": text[:200],
            "fallback": True,
        }
