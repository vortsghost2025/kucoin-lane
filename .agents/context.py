"""
Shared Agent Context Management for KuCoin Lane.

Provides atomic read/write with file locking for the shared agent-context.json file.
All 8 specialized sub-agents use this for state sharing.
"""

import json
import os
import time
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from contextlib import contextmanager

# Cross-platform file locking
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


CONTEXT_PATH = Path(__file__).parent.parent / "data" / "agent-context.json"
LOCK_PATH = Path(__file__).parent.parent / "data" / "agent-context.lock"


DEFAULT_CONTEXT = {
    "schema_version": 1,
    "updated_at": None,
    "cycle": 0,
    "pipeline": {
        "status": "idle",  # idle, running, paused, error
        "last_cycle_completed": None,
        "cycles_completed": 0,
        "cycles_failed": 0,
    },
    "positions": {
        "open": [],
        "closed_recent": [],
        "total_pnl_usd": 0.0,
        "win_rate": 0.0,
        "total_trades": 0,
    },
    "creator_registry": {
        "total_creators": 0,
        "alpha_creators": [],
        "serial_launchers": [],
        "last_resolved": None,
    },
    "circuit_breakers": {
        "global": {"tripped": False, "reason": None, "at": None},
        "portfolio": {"tripped": False, "reason": None, "at": None},
        "per_token": {},
    },
    "market_regime": {
        "classification": "unknown",  # trending, ranging, volatile, unknown
        "confidence": 0.0,
        "last_updated": None,
        "indicators": {},
    },
    "scan_results": {
        "phantom": {"tokens": [], "last_scan": None, "errors": []},
        "pumpfun": {"tokens": [], "last_scan": None, "errors": []},
        "birdeye": {"tokens": [], "last_scan": None, "errors": []},
        "dexscreener": {"tokens": [], "last_scan": None, "errors": []},
        "polymarket": {"tokens": [], "last_scan": None, "errors": []},
    },
    "health": {
        "last_health_check": None,
        "anomalies": [],
        "alerts": [],
        "api_latency": {},
    },
    "metadata": {
        "started_at": None,
        "version": "1.0.0",
        "environment": "paper",  # paper, live
    }
}


class ContextLock:
    """File-based lock with timeout for cross-process synchronization."""
    
    def __init__(self, lock_path: Path, timeout: float = 10.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self._fd = None
    
    def acquire(self) -> bool:
        start = time.time()
        while time.time() - start < self.timeout:
            try:
                self._fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return True
            except FileExistsError:
                time.sleep(0.05)
        return False
    
    def release(self):
        if self._fd is not None:
            os.close(self._fd)
            try:
                os.unlink(self.lock_path)
            except FileNotFoundError:
                pass
            self._fd = None
    
    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"Could not acquire lock within {self.timeout}s")
        return self
    
    def __exit__(self, *args):
        self.release()


def _load_raw() -> Dict[str, Any]:
    """Load context without locking (internal use)."""
    if not CONTEXT_PATH.exists():
        return DEFAULT_CONTEXT.copy()
    try:
        with open(CONTEXT_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return DEFAULT_CONTEXT.copy()


def _save_raw(data: Dict[str, Any]) -> bool:
    """Save context without locking (internal use)."""
    try:
        CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = CONTEXT_PATH.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        tmp_path.replace(CONTEXT_PATH)
        return True
    except OSError:
        return False


@contextmanager
def locked_context():
    """Context manager for atomic read-modify-write with locking."""
    lock = ContextLock(LOCK_PATH)
    acquired = lock.acquire()
    if not acquired:
        raise TimeoutError("Context lock timeout")
    try:
        data = _load_raw()
        yield data
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_raw(data)
    finally:
        lock.release()


def read_context() -> Dict[str, Any]:
    """Read current context (with lock for consistency)."""
    with locked_context() as data:
        return data.copy()


def write_context(data: Dict[str, Any]) -> bool:
    """Write entire context (with lock)."""
    with locked_context() as ctx:
        ctx.update(data)
    return True


def update_context(updates: Dict[str, Any]) -> bool:
    """Atomically update specific keys in context."""
    with locked_context() as data:
        _deep_update(data, updates)
    return True


def _deep_update(target: Dict[str, Any], updates: Dict[str, Any]):
    """Recursively update nested dictionaries."""
    for key, value in updates.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def get_cycle() -> int:
    """Get current cycle number."""
    with locked_context() as data:
        return data.get("cycle", 0)


def increment_cycle() -> int:
    """Increment and return new cycle number."""
    with locked_context() as data:
        data["cycle"] = data.get("cycle", 0) + 1
        return data["cycle"]


def set_pipeline_status(status: str, **extra):
    """Update pipeline status with optional extra fields."""
    with locked_context() as data:
        data["pipeline"]["status"] = status
        data["pipeline"].update(extra)


def record_scan_result(source: str, tokens: list, errors: list = None):
    """Record scan results for a DEX source."""
    with locked_context() as data:
        data["scan_results"][source] = {
            "tokens": tokens,
            "last_scan": datetime.now(timezone.utc).isoformat(),
            "errors": errors or [],
        }


def record_position_open(position: Dict[str, Any]):
    """Add an open position."""
    with locked_context() as data:
        data["positions"]["open"].append(position)


def record_position_close(position: Dict[str, Any], pnl_usd: float):
    """Move position from open to closed, update P&L."""
    with locked_context() as data:
        # Remove from open
        data["positions"]["open"] = [
            p for p in data["positions"]["open"] 
            if p.get("mint") != position.get("mint")
        ]
        # Add to closed
        closed = position.copy()
        closed["closed_at"] = datetime.now(timezone.utc).isoformat()
        closed["pnl_usd"] = pnl_usd
        data["positions"]["closed_recent"].append(closed)
        # Trim closed history
        if len(data["positions"]["closed_recent"]) > 100:
            data["positions"]["closed_recent"] = data["positions"]["closed_recent"][-100:]
        # Update totals
        data["positions"]["total_pnl_usd"] += pnl_usd
        data["positions"]["total_trades"] += 1
        wins = sum(1 for p in data["positions"]["closed_recent"] if p.get("pnl_usd", 0) > 0)
        data["positions"]["win_rate"] = wins / len(data["positions"]["closed_recent"]) if data["positions"]["closed_recent"] else 0.0


def trip_circuit_breaker(name: str, reason: str):
    """Trip a circuit breaker."""
    with locked_context() as data:
        if name in data["circuit_breakers"]:
            data["circuit_breakers"][name] = {
                "tripped": True,
                "reason": reason,
                "at": datetime.now(timezone.utc).isoformat(),
            }


def reset_circuit_breaker(name: str):
    """Reset a circuit breaker."""
    with locked_context() as data:
        if name in data["circuit_breakers"]:
            data["circuit_breakers"][name] = {"tripped": False, "reason": None, "at": None}


def check_circuit_breakers() -> Dict[str, bool]:
    """Check all circuit breakers, return dict of tripped status."""
    with locked_context() as data:
        return {k: v.get("tripped", False) for k, v in data["circuit_breakers"].items()}


def update_market_regime(classification: str, confidence: float, indicators: dict = None):
    """Update market regime classification."""
    with locked_context() as data:
        data["market_regime"] = {
            "classification": classification,
            "confidence": confidence,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "indicators": indicators or {},
        }


def record_anomaly(anomaly: Dict[str, Any]):
    """Record an anomaly for monitoring."""
    with locked_context() as data:
        anomaly["detected_at"] = datetime.now(timezone.utc).isoformat()
        data["health"]["anomalies"].append(anomaly)
        # Keep last 50 anomalies
        if len(data["health"]["anomalies"]) > 50:
            data["health"]["anomalies"] = data["health"]["anomalies"][-50:]


def record_alert(alert: Dict[str, Any]):
    """Record an alert."""
    with locked_context() as data:
        alert["alerted_at"] = datetime.now(timezone.utc).isoformat()
        data["health"]["alerts"].append(alert)
        if len(data["health"]["alerts"]) > 50:
            data["health"]["alerts"] = data["health"]["alerts"][-50:]


def update_api_latency(service: str, latency_ms: float):
    """Record API latency for health monitoring."""
    with locked_context() as data:
        if service not in data["health"]["api_latency"]:
            data["health"]["api_latency"][service] = []
        data["health"]["api_latency"][service].append({
            "latency_ms": latency_ms,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        # Keep last 20 per service
        if len(data["health"]["api_latency"][service]) > 20:
            data["health"]["api_latency"][service] = data["health"]["api_latency"][service][-20:]


# CLI for testing
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python context.py [read|write|update|cycle|status]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "read":
        print(json.dumps(read_context(), indent=2, default=str))
    elif cmd == "cycle":
        print(f"Current cycle: {get_cycle()}")
        print(f"Next cycle: {increment_cycle()}")
    elif cmd == "status":
        ctx = read_context()
        print(f"Pipeline: {ctx['pipeline']['status']}")
        print(f"Cycle: {ctx['cycle']}")
        print(f"Open positions: {len(ctx['positions']['open'])}")
        print(f"Total P&L: ${ctx['positions']['total_pnl_usd']:.2f}")
        print(f"Circuit breakers: {check_circuit_breakers()}")
    elif cmd == "init":
        # Initialize with defaults
        write_context(DEFAULT_CONTEXT)
        print("Context initialized")
    else:
        print(f"Unknown command: {cmd}")