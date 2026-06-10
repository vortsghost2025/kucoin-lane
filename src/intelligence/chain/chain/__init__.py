"""Chain intelligence: on-chain safety checks and pre-launch scanning.

Wraps PreLaunchScanner and SafetyGuard as BaseAgent-compatible classes
so they integrate with the orchestrator and share the standard message format.
"""

from ...base_agent import BaseAgent, AgentStatus
from .prelaunch_scanner import PreLaunchScanner, KNOWN_LAUNCH_COMMUNITIES
from .safety_guard import SafetyGuard, RISK_TIERS, RED_FLAGS, SAFE_SIGNALS
from .helius_provider import HeliusProvider

__all__ = [
    "PreLaunchScannerAgent",
    "SafetyGuardAgent",
    "PreLaunchScanner",
    "SafetyGuard",
    "HeliusProvider",
    "KNOWN_LAUNCH_COMMUNITIES",
    "RISK_TIERS",
    "RED_FLAGS",
    "SAFE_SIGNALS",
]


class PreLaunchScannerAgent(BaseAgent):
    """BaseAgent wrapper around PreLaunchScanner.

    Execute actions:
      - "scan_new"       → scan_pumpfun_new(limit)
      - "scan_callouts"  → scan_pumpfun_callouts(channel, limit)
      - "social_links"   → get_token_social_links(mint)
      - "communities"    → discover_launch_communities()
    """

    def __init__(self, config=None):
        super().__init__("prelaunch_scanner", config)
        rpc = self.config.get("solana_rpc_url") if self.config else None
        self._scanner = PreLaunchScanner(rpc_url=rpc)

    def execute(self, action: str = "scan_new", **kwargs) -> dict:
        self.log_execution_start(action)
        try:
            if action == "scan_new":
                limit = kwargs.get("limit", 20)
                result = self._scanner.scan_pumpfun_new(limit=limit)
            elif action == "scan_callouts":
                channel = kwargs.get("channel", "")
                limit = kwargs.get("limit", 20)
                result = self._scanner.scan_pumpfun_callouts(channel=channel, limit=limit)
            elif action == "social_links":
                mint = kwargs.get("mint", "")
                result = self._scanner.get_token_social_links(mint)
            elif action == "communities":
                result = self._scanner.discover_launch_communities()
            else:
                self.log_execution_end(action, success=False)
                return self.create_message(action, error=f"Unknown action: {action}", success=False)

            self.log_execution_end(action, success=True)
            return self.create_message(action, data={"results": result})
        except Exception as e:
            self.log_execution_end(action, success=False)
            return self.create_message(action, error=str(e), success=False)


class SafetyGuardAgent(BaseAgent):
    """BaseAgent wrapper around SafetyGuard.

    Execute actions:
      - "check"        → check_token(mint, name, extra)
      - "batch_check"  → batch_check(tokens)
      - "filter_safe"  → filter_safe(tokens, max_risk_level)
    """

    def __init__(self, config=None):
        super().__init__("safety_guard", config)
        rpc = self.config.get("solana_rpc_url") if self.config else None
        self._guard = SafetyGuard(rpc_url=rpc)

    def execute(self, action: str = "check", **kwargs) -> dict:
        self.log_execution_start(action)
        try:
            if action == "check":
                result = self._guard.check_token(
                    mint=kwargs.get("mint", ""),
                    token_name=kwargs.get("name", ""),
                    extra=kwargs.get("extra"),
                )
            elif action == "batch_check":
                result = self._guard.batch_check(kwargs.get("tokens", []))
            elif action == "filter_safe":
                result = self._guard.filter_safe(
                    tokens=kwargs.get("tokens", []),
                    max_risk_level=kwargs.get("max_risk_level", 1),
                )
            else:
                self.log_execution_end(action, success=False)
                return self.create_message(action, error=f"Unknown action: {action}", success=False)

            self.log_execution_end(action, success=True)
            return self.create_message(action, data={"results": result})
        except Exception as e:
            self.log_execution_end(action, success=False)
            return self.create_message(action, error=str(e), success=False)
