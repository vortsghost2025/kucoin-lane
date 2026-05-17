import os
import pickle
import tempfile
import pytest
from pathlib import Path
from src.checkpoint_manager import CheckpointManager


class TestCheckpointManager:
    @pytest.fixture
    def state_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp)

    @pytest.fixture
    def mgr(self, state_dir):
        return CheckpointManager(state_dir=str(state_dir))

    def test_init_creates_state_dir(self, state_dir):
        target = state_dir / "sub"
        mgr = CheckpointManager(state_dir=str(target))
        assert target.exists()
        assert target.is_dir()

    def test_init_with_on_checkpoint(self, state_dir):
        called = False
        def cb(state):
            nonlocal called
            called = True
        mgr = CheckpointManager(state_dir=str(state_dir), on_checkpoint=cb)
        mgr.save_checkpoint({"key": "val"}, "test")
        assert called

    def test_save_and_load_checkpoint(self, mgr):
        state = {"pair": "SOL/USDT", "price": 100.0}
        path = mgr.save_checkpoint(state, "test_ckpt")
        assert path.exists()
        loaded = mgr.load_checkpoint("test_ckpt")
        assert loaded == state

    def test_load_missing_checkpoint(self, mgr):
        assert mgr.load_checkpoint("nonexistent") is None

    def test_load_corrupted_checkpoint(self, mgr):
        path = mgr.state_dir / "bad.ckpt"
        path.write_bytes(b"not pickle data")
        assert mgr.load_checkpoint("bad") is None

    def test_list_checkpoints(self, mgr):
        mgr.save_checkpoint({"a": 1}, "ckpt_a")
        mgr.save_checkpoint({"b": 2}, "ckpt_b")
        names = mgr.list_checkpoints()
        assert "ckpt_a" in names
        assert "ckpt_b" in names

    def test_delete_checkpoint(self, mgr):
        mgr.save_checkpoint({"x": 1}, "to_delete")
        assert mgr.state_dir / "to_delete.ckpt" in mgr.state_dir.glob("*.ckpt")
        deleted = mgr.delete_checkpoint("to_delete")
        assert deleted is True
        assert not (mgr.state_dir / "to_delete.ckpt").exists()

    def test_delete_nonexistent(self, mgr):
        assert mgr.delete_checkpoint("ghost") is False

    def test_set_pending_state(self, mgr):
        mgr.set_pending_state({"emergency": True})
        assert mgr._pending_state == {"emergency": True}

    def test_callback_failure_does_not_prevent_save(self, state_dir):
        def failing_cb(state):
            raise RuntimeError("callback failed")
        mgr = CheckpointManager(state_dir=str(state_dir), on_checkpoint=failing_cb)
        path = mgr.save_checkpoint({"ok": 1}, "still_works")
        assert path.exists()
        loaded = mgr.load_checkpoint("still_works")
        assert loaded == {"ok": 1}
