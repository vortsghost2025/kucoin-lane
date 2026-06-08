"""Social intelligence: Telegram signal extraction, XAI analysis, and scoring.

Wraps SocialSignalScorer, XAIProvider, and TelegramProvider as BaseAgent-compatible
classes so they integrate with the orchestrator and share the standard message format.
"""

from ...base_agent import BaseAgent, AgentStatus
from .scorer import SocialSignalScorer, SocialScore, SIGNAL_WEIGHTS, SENTIMENT_MAP, VOLUME_MAP
from .xai_provider import XAIProvider
from .telegram_provider import TelegramProvider, CRYPTO_PATTERNS, DEFAULT_CHANNELS

__all__ = [
    "SocialScorerAgent",
    "XAIProviderAgent",
    "TelegramProviderAgent",
    "SocialSignalScorer",
    "SocialScore",
    "XAIProvider",
    "TelegramProvider",
    "SIGNAL_WEIGHTS",
    "SENTIMENT_MAP",
    "VOLUME_MAP",
    "CRYPTO_PATTERNS",
    "DEFAULT_CHANNELS",
]


class SocialScorerAgent(BaseAgent):
    """BaseAgent wrapper around SocialSignalScorer.

    Execute actions:
    - "score" → score_telegram_message(text, views, forwards, replies)
    - "batch_score" → score multiple messages at once
    """

    def __init__(self, config=None):
        super().__init__("social_scorer", config)
        self._scorer = SocialSignalScorer()

    def execute(self, action: str = "score", **kwargs) -> dict:
        self.log_execution_start(action)
        try:
            if action == "score":
                result = self._scorer.score_telegram_message(
                    text=kwargs.get("text", ""),
                    views=kwargs.get("views", 0),
                    forwards=kwargs.get("forwards", 0),
                    replies=kwargs.get("replies", 0),
                )
                data = self._score_to_dict(result)
            elif action == "batch_score":
                messages = kwargs.get("messages", [])
                scores = []
                for m in messages:
                    s = self._scorer.score_telegram_message(
                        text=m.get("text", ""),
                        views=m.get("views", 0),
                        forwards=m.get("forwards", 0),
                        replies=m.get("replies", 0),
                    )
                    scores.append(self._score_to_dict(s))
                data = {"scores": scores}
            else:
                self.log_execution_end(action, success=False)
                return self.create_message(action, error=f"Unknown action: {action}", success=False)

            self.log_execution_end(action, success=True)
            return self.create_message(action, data=data)
        except Exception as e:
            self.log_execution_end(action, success=False)
            return self.create_message(action, error=str(e), success=False)

    @staticmethod
    def _score_to_dict(score: SocialScore) -> dict:
        return {
            "composite": score.composite,
            "signal_score": score.signal_score,
            "engagement": score.engagement,
            "has_dex_link": score.has_dex_link,
            "has_contract": score.has_contract,
            "signals": score.signals,
            "sentiment": score.sentiment,
            "volume": score.volume,
            "alert_level": score.alert_level,
        }


class XAIProviderAgent(BaseAgent):
    """BaseAgent wrapper around XAIProvider.

    Execute actions:
    - "analyze" → analyze_social_post(text, context)
    - "batch_analyze" → analyze_telegram_batch(messages, context)
    """

    def __init__(self, config=None):
        super().__init__("xai_provider", config)
        self._provider = XAIProvider()

    def execute(self, action: str = "analyze", **kwargs) -> dict:
        self.log_execution_start(action)
        try:
            if not self._provider.available:
                self.log_execution_end(action, success=False)
                return self.create_message(action, error="XAI_API_KEY not set", success=False)
            if action == "analyze":
                result = self._provider.analyze_social_post(
                    text=kwargs.get("text", ""),
                    context=kwargs.get("context", ""),
                )
            elif action == "batch_analyze":
                result = self._provider.analyze_telegram_batch(
                    messages=kwargs.get("messages", []),
                    context=kwargs.get("context", ""),
                )
            else:
                self.log_execution_end(action, success=False)
                return self.create_message(action, error=f"Unknown action: {action}", success=False)

            self.log_execution_end(action, success=True)
            return self.create_message(action, data={"analysis": result})
        except Exception as e:
            self.log_execution_end(action, success=False)
            return self.create_message(action, error=str(e), success=False)


class TelegramProviderAgent(BaseAgent):
    """BaseAgent wrapper around TelegramProvider.

    Execute actions:
    - "extract_signals" → extract_signals(text)
    - "get_recent" → get_recent_messages(limit, channel)
    - "listen" → listen(limit, channel) — async, returns empty if no telethon
    """

    def __init__(self, config=None):
        super().__init__("telegram_provider", config)
        self._provider = TelegramProvider()

    def execute(self, action: str = "extract_signals", **kwargs) -> dict:
        self.log_execution_start(action)
        try:
            if action == "extract_signals":
                result = self._provider.extract_signals(kwargs.get("text", ""))
            elif action == "get_recent":
                result = self._provider.get_recent_messages(
                    limit=kwargs.get("limit", 50),
                    channel=kwargs.get("channel"),
                )
            elif action == "listen":
                result = self._provider.get_recent_messages(
                    limit=kwargs.get("limit", 50),
                    channel=kwargs.get("channel"),
                )
            else:
                self.log_execution_end(action, success=False)
                return self.create_message(action, error=f"Unknown action: {action}", success=False)

            self.log_execution_end(action, success=True)
            return self.create_message(action, data={"results": result, "available": self._provider.available})
        except Exception as e:
            self.log_execution_end(action, success=False)
            return self.create_message(action, error=str(e), success=False)
