"""
Base Agent Class

Base class for all agents in the multi-agent trading system.
Provides common functionality for logging, state management, and communication.
"""

import logging
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class AgentStatus(Enum):
    IDLE = "idle"
    WORKING = "working"
    ERROR = "error"
    PAUSED = "paused"


class BaseAgent:
    """
    Base class for all trading bot agents.

    Each agent has a single responsibility and communicates with others
    through the orchestrator.

    This base class provides:
    - Logging infrastructure
    - Status tracking
    - Standard message format
    - Error handling
    """

    def __init__(self, agent_name: str, config: Optional[Dict[str, Any]] = None):
        self.agent_name = agent_name
        self.config = config or {}
        self.status = AgentStatus.IDLE
        self.last_error: Optional[str] = None
        self.execution_count = 0
        self.last_execution_time: Optional[datetime] = None
        self.logger = logging.getLogger(agent_name)
        self._setup_logging()

    def _setup_logging(self) -> None:
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                f"[%(asctime)s] [{self.agent_name}] %(levelname)s: %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def set_status(self, status: AgentStatus, error: Optional[str] = None) -> None:
        self.status = status
        if error:
            self.last_error = error
            self.logger.error(error)
        else:
            self.last_error = None

    def create_message(
        self,
        action: str,
        data: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        message = {
            "agent": self.agent_name,
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": success,
            "data": data or {},
            "error": error,
        }
        return message

    def execute(self, *args, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError("Subclasses must implement execute()")

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        return True, None

    def get_status_report(self) -> Dict[str, Any]:
        return {
            "name": self.agent_name,
            "status": self.status.value,
            "execution_count": self.execution_count,
            "last_execution_time": self.last_execution_time.isoformat()
            if self.last_execution_time
            else None,
            "last_error": self.last_error,
        }

    def log_execution_start(self, action: str) -> None:
        self.logger.info(f"Starting: {action}")
        self.status = AgentStatus.WORKING

    def log_execution_end(self, action: str, success: bool = True) -> None:
        if success:
            self.logger.info(f"Completed: {action}")
            self.status = AgentStatus.IDLE
        else:
            self.logger.warning(f"Failed: {action}")
            self.status = AgentStatus.ERROR
        self.execution_count += 1
        self.last_execution_time = datetime.now(timezone.utc)
