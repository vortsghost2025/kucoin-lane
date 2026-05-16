"""
Checkpoint Manager - Signal-based state persistence.
=====================================================

Ported from kucoin-margin-bot src/checkpoint_manager.py.

Features:
- Save/load trading state with pickle serialization
- Atomic writes (with atomicwrites package if available)
- SIGTERM/SIGINT signal handlers trigger automatic checkpoint
- Optional on_checkpoint callback for pre-save hooks
"""

import logging
import os
import pickle
import signal
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import atomicwrites

    HAS_ATOMIC_WRITES = True
except ImportError:
    HAS_ATOMIC_WRITES = False


class CheckpointManager:
    def __init__(
        self,
        state_dir: str = "./state",
        on_checkpoint: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.on_checkpoint = on_checkpoint
        self._pending_state: Optional[Dict[str, Any]] = None
        self._setup_signal_handlers()

    def save_checkpoint(
        self, state_dict: Dict[str, Any], checkpoint_name: str = "latest"
    ) -> Path:
        checkpoint_path = self.state_dir / f"{checkpoint_name}.ckpt"

        if self.on_checkpoint:
            try:
                self.on_checkpoint(state_dict)
            except Exception as exc:
                logger.warning("on_checkpoint callback failed: %s", exc)

        data = pickle.dumps(state_dict, protocol=pickle.HIGHEST_PROTOCOL)

        if HAS_ATOMIC_WRITES:
            try:
                with atomicwrites.atomic_write(
                    str(checkpoint_path), mode="wb", overwrite=True
                ) as f:
                    f.write(data)
                logger.info("Checkpoint saved (atomic): %s", checkpoint_path)
                return checkpoint_path
            except Exception as exc:
                logger.warning("Atomic write failed, falling back: %s", exc)

        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(self.state_dir), suffix=".ckpt.tmp")
        try:
            with os.fdopen(tmp_fd, "wb") as f:
                f.write(data)
            shutil.move(tmp_path, str(checkpoint_path))
            logger.info("Checkpoint saved (fallback): %s", checkpoint_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        return checkpoint_path

    def load_checkpoint(
        self, checkpoint_name: str = "latest"
    ) -> Optional[Dict[str, Any]]:
        checkpoint_path = self.state_dir / f"{checkpoint_name}.ckpt"

        if not checkpoint_path.exists():
            logger.info("No checkpoint found: %s", checkpoint_path)
            return None

        try:
            with open(checkpoint_path, "rb") as f:
                state = pickle.load(f)
            logger.info("Checkpoint loaded: %s", checkpoint_path)
            return state
        except Exception as exc:
            logger.error("Failed to load checkpoint %s: %s", checkpoint_path, exc)
            return None

    def list_checkpoints(self) -> list:
        ckpts = sorted(self.state_dir.glob("*.ckpt"))
        return [c.stem for c in ckpts]

    def delete_checkpoint(self, checkpoint_name: str) -> bool:
        checkpoint_path = self.state_dir / f"{checkpoint_name}.ckpt"
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.info("Checkpoint deleted: %s", checkpoint_path)
            return True
        return False

    def set_pending_state(self, state_dict: Dict[str, Any]) -> None:
        self._pending_state = state_dict

    def _setup_signal_handlers(self) -> None:
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self._checkpoint_signal_handler)
            except (OSError, ValueError):
                pass

    def _checkpoint_signal_handler(self, signum: int, frame: Any) -> None:
        sig_name = signal.Signals(signum).name
        logger.warning("Received %s — saving emergency checkpoint", sig_name)

        if self._pending_state is not None:
            try:
                self.save_checkpoint(self._pending_state, checkpoint_name="emergency")
            except Exception as exc:
                logger.error("Emergency checkpoint failed: %s", exc)

        raise SystemExit(128 + signum)
