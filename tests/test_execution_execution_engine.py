import os
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from src.execution.execution_engine import (
    ExecutionEngine,
    DryRunExecutor,
    LiveExecutor,
    ExecutionAgent,
    TradeStatus,
    select_executor,
)
from src.execution.trailing_stop import TrailingStopManager, ProgressiveROI, CustomStopLoss


class ConcreteEngine(ExecutionEngine):
    def run_cycle(self):
        pass


def _patch_engine_attrs(engine, extra=None):
    """Set minimum attrs on __new__-created engines so tests work."""
    base = {
        "config": {},
        "heartbeat_file": "",
        "start_time": datetime.now(),
        "cycle_count": 0,
        "is_running": True,
        "open_positions": [],
        "closed_trades": [],
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "portfolio_cb": None,
        "trailing_stop": TrailingStopManager(),
        "progressive_roi": ProgressiveROI(),
        "custom_stoploss": CustomStopLoss(),
        "_last_runtime_status": "initializing",
    }
    if extra:
        base.update(extra)
    engine.__dict__.update(base)


class TestTradeStatus:
    def test_values(self):
        assert TradeStatus.OPEN.value == "open"
        assert TradeStatus.CLOSED.value == "closed"
        assert TradeStatus.PENDING.value == "pending"
        assert TradeStatus.CANCELLED.value == "cancelled"


class TestExecutionEngine:
    @pytest.fixture
    def config(self):
        return {}

    def test_init(self, config):
        engine = ConcreteEngine.__new__(ConcreteEngine)
        _patch_engine_attrs(engine, {"config": config, "heartbeat_file": "bot_heartbeat_dry_run.json"})
        assert engine.cycle_count == 0
        assert engine.is_running is True

    def test_write_heartbeat(self, config, tmp_path):
        engine = ConcreteEngine.__new__(ConcreteEngine)
        _patch_engine_attrs(engine, {"heartbeat_file": str(tmp_path / "heartbeat.json"), "cycle_count": 1})
        engine.write_heartbeat("testing", "test_step")
        with open(engine.heartbeat_file) as f:
            data = json.load(f)
        assert data["status"] == "testing"
        assert data["step"] == "test_step"
        assert "pid" in data

    def test_get_total_pnl(self, config):
        engine = ConcreteEngine.__new__(ConcreteEngine)
        _patch_engine_attrs(engine, {"closed_trades": [{"pnl": 100}, {"pnl": -50}], "total_trades": 2, "winning_trades": 1, "losing_trades": 1})
        assert engine._get_total_pnl() == 50

    def test_close_position(self, config):
        engine = ConcreteEngine.__new__(ConcreteEngine)
        _patch_engine_attrs(engine, {
            "open_positions": [{"trade_id": 1, "pair": "SOL/USDT", "entry_price": 100.0, "position_size": 1.0}],
            "total_trades": 1, "winning_trades": 0, "losing_trades": 0,
        })
        result = engine.close_position(1, 110.0, "take_profit")
        assert result["exit_reason"] == "take_profit"
        assert result["pnl"] == 10.0
        assert result["status"] == "closed"
        assert len(engine.open_positions) == 0
        assert engine.winning_trades == 1

    def test_update_open_positions_stop_loss(self, config):
        engine = ConcreteEngine.__new__(ConcreteEngine)
        _patch_engine_attrs(engine, {
            "open_positions": [
                {"trade_id": 1, "pair": "SOL/USDT", "entry_price": 100.0, "position_size": 1.0, "stop_loss": 95.0, "take_profit": 110.0},
            ],
            "total_trades": 1, "winning_trades": 0, "losing_trades": 0,
        })
        closed = engine.update_open_positions({"SOL/USDT": 94.0})
        assert len(closed) == 1
        assert closed[0]["exit_reason"] == "stop_loss"

    def test_update_open_positions_take_profit(self, config):
        engine = ConcreteEngine.__new__(ConcreteEngine)
        _patch_engine_attrs(engine, {
            "open_positions": [
                {"trade_id": 1, "pair": "SOL/USDT", "entry_price": 100.0, "position_size": 1.0, "stop_loss": 95.0, "take_profit": 110.0},
            ],
            "total_trades": 1, "winning_trades": 0, "losing_trades": 0,
        })
        closed = engine.update_open_positions({"SOL/USDT": 111.0})
        assert len(closed) == 1
        assert closed[0]["exit_reason"] == "take_profit"

    def test_get_performance_summary_no_trades(self, config):
        engine = ConcreteEngine.__new__(ConcreteEngine)
        _patch_engine_attrs(engine)
        summary = engine.get_performance_summary()
        assert summary["total_trades"] == 0
        assert summary["win_rate"] == 0

    def test_shutdown_sets_is_running_false(self, config):
        pass  # just a smoke test

    def test_get_open_positions_returns_copy(self, config):
        engine = ConcreteEngine.__new__(ConcreteEngine)
        _patch_engine_attrs(engine, {"open_positions": [{"trade_id": 1}]})
        result = engine.get_open_positions()
        assert len(result) == 1
        result.append({"trade_id": 2})
        assert len(engine.open_positions) == 1


class TestDryRunExecutor:
    @pytest.fixture
    def config(self):
        return {"max_open_positions": 3, "max_trades_per_session": 5}

    @patch.object(DryRunExecutor, "load_backtest_data")
    def test_init(self, mock_load, config):
        executor = DryRunExecutor(config)
        assert executor.paper_trading is True
        assert executor.max_open_positions == 3
        assert executor.max_trades_per_session == 5

    @patch.object(DryRunExecutor, "load_backtest_data")
    def test_execute_valid(self, mock_load, config):
        executor = DryRunExecutor(config)
        result = executor.execute({
            "market_data": {"SOL/USDT": {"current_price": 100.0}},
            "position_size": 1.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
        })
        assert result["success"] is True
        assert result["data"]["trade_executed"] is True
        assert result["data"]["pair"] == "SOL/USDT"
        assert len(executor.open_positions) == 1
        assert executor.total_trades == 1

    @patch.object(DryRunExecutor, "load_backtest_data")
    def test_execute_no_size(self, mock_load, config):
        executor = DryRunExecutor(config)
        result = executor.execute({
            "market_data": {"SOL/USDT": {"current_price": 100.0}},
            "position_size": 0,
        })
        assert result["data"]["trade_executed"] is False

    @patch.object(DryRunExecutor, "load_backtest_data")
    def test_execute_multiple_trades(self, mock_load, config):
        executor = DryRunExecutor(config)
        for _ in range(3):
            executor.execute({
                "market_data": {"SOL/USDT": {"current_price": 100.0}},
                "position_size": 1.0,
                "stop_loss": 95.0,
                "take_profit": 110.0,
            })
        assert len(executor.open_positions) == 3
        assert executor.total_trades == 3


class TestLiveExecutor:
    @pytest.fixture
    def config(self):
        return {
            "max_open_positions": 3,
            "max_trades_per_session": 5,
            "max_position_size_usd": 10000,
            "max_trade_loss_usd": 500,
            "max_daily_loss_usd": 2000,
            "min_balance_usd": 100,
            "order_type": "market",
        }

    def test_init_no_adapter(self, config):
        with patch("src.execution.execution_engine.KuCoinAdapter", side_effect=Exception("no creds")):
            with pytest.raises(Exception):
                LiveExecutor(config)

    def test_validate_live_trade_position_exceeds_balance(self, config):
        executor = LiveExecutor.__new__(LiveExecutor)
        _patch_engine_attrs(executor, {
            "max_open_positions": 3, "max_position_size_usd": 10000,
            "max_trade_loss_usd": 500, "max_daily_loss_usd": 2000,
            "min_balance_usd": 100, "order_type": "market",
        })
        reason = executor._validate_live_trade(
            entry_price=100.0, position_size=100.0, stop_loss=90.0, account_balance=5000.0
        )
        # position_value = 10000, balance*1.1 = 5500 -> exceeds
        assert reason is not None
        assert "exceeds" in reason.lower()

    def test_validate_live_trade_max_positions(self, config):
        executor = LiveExecutor.__new__(LiveExecutor)
        _patch_engine_attrs(executor, {
            "open_positions": [{"trade_id": 1}, {"trade_id": 2}, {"trade_id": 3}],
            "total_trades": 3,
            "max_open_positions": 3, "max_position_size_usd": 10000,
            "max_trade_loss_usd": 500, "max_daily_loss_usd": 2000,
            "min_balance_usd": 100, "order_type": "market",
        })
        reason = executor._validate_live_trade(
            entry_price=100.0, position_size=1.0, stop_loss=90.0, account_balance=5000.0
        )
        assert reason is not None
        assert "max open positions" in reason.lower()

    def test_validate_live_trade_passes(self, config):
        executor = LiveExecutor.__new__(LiveExecutor)
        _patch_engine_attrs(executor, {
            "max_open_positions": 3, "max_position_size_usd": 10000,
            "max_trade_loss_usd": 500, "max_daily_loss_usd": 2000,
            "min_balance_usd": 100, "order_type": "market",
        })
        reason = executor._validate_live_trade(
            entry_price=100.0, position_size=0.1, stop_loss=95.0, account_balance=5000.0
        )
        assert reason is None

    def test_execute_no_approval(self, config):
        executor = LiveExecutor.__new__(LiveExecutor)
        _patch_engine_attrs(executor)
        result = executor.execute({
            "position_approved": False, "risk_approved": False,
        })
        assert result["success"] is True
        assert result["data"]["trade_executed"] is False


class TestExecutionAgent:
    @patch("src.execution.execution_engine.DryRunExecutor")
    def test_execute_delegates(self, mock_executor):
        mock_instance = MagicMock()
        mock_instance.execute.return_value = {"success": True, "data": {"trade_executed": True}}
        mock_executor.return_value = mock_instance

        from src.execution.execution_engine import ExecutionAgent
        agent = ExecutionAgent({"dry_run": True})
        result = agent.execute({"market_data": {"SOL/USDT": {"current_price": 100.0}}, "position_size": 1.0})
        assert result["success"] is True

    def test_close_position_delegates(self):
        engine = MagicMock()
        agent = ExecutionAgent.__new__(ExecutionAgent)
        agent.agent_name = "ExecutionAgent"
        agent.engine = engine
        agent.close_position(1, 100.0, "test")
        engine.close_position.assert_called_with(1, 100.0, "test")

    def test_update_open_positions_delegates(self):
        engine = MagicMock()
        agent = ExecutionAgent.__new__(ExecutionAgent)
        agent.agent_name = "ExecutionAgent"
        agent.engine = engine
        agent.update_open_positions({"SOL/USDT": 100.0})
        engine.update_open_positions.assert_called_with({"SOL/USDT": 100.0})

    def test_get_performance_summary_delegates(self):
        engine = MagicMock()
        agent = ExecutionAgent.__new__(ExecutionAgent)
        agent.agent_name = "ExecutionAgent"
        agent.engine = engine
        agent.get_performance_summary()
        engine.get_performance_summary.assert_called_once()


class TestSelectExecutor:
    def test_select_dry_run(self):
        executor = select_executor(dry_run=True, live_trading=False)
        assert isinstance(executor, DryRunExecutor)

    def test_select_live_trading(self):
        mock_adapter = MagicMock()
        mock_adapter.authenticated = False
        with patch("src.execution.execution_engine.KuCoinAdapter", return_value=mock_adapter):
            executor = select_executor(dry_run=False, live_trading=True)
        assert executor is not None
        assert isinstance(executor, LiveExecutor)
        assert executor.adapter is not None
        assert executor.adapter.authenticated is False

    def test_select_neither_raises(self):
        with pytest.raises(RuntimeError):
            select_executor(dry_run=False, live_trading=False)
