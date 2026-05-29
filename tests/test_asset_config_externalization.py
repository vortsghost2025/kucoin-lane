import importlib
import json

from src import config as cfg
from src.intelligence.backtester import BacktestingAgent
from src.risk.risk_manager import RiskManagementAgent


def test_asset_profiles_load_from_json_file(tmp_path, monkeypatch):
    profile_path = tmp_path / "asset_profiles.json"
    profile_path.write_text(
        json.dumps(
            {
                "risk": {
                    "pairs": {
                        "XRP/USDT": {
                            "min_signal_strength_adjustment": 0.0,
                            "stop_loss_adjustment": 0.9,
                            "position_size_multiplier": 0.7,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("ASSET_CONFIGS_PATH", str(profile_path))
    importlib.reload(cfg)

    assert "XRP/USDT" in cfg.RISK_CONFIG["asset_configs"]
    assert (
        cfg.RISK_CONFIG["asset_configs"]["XRP/USDT"]["position_size_multiplier"] == 0.7
    )
    monkeypatch.delenv("ASSET_CONFIGS_PATH", raising=False)
    importlib.reload(cfg)


def test_risk_manager_supports_non_default_pair_with_generic_fallback():
    agent = RiskManagementAgent(
        {
            "account_balance": 1000.0,
            "risk_per_trade": 0.01,
            "min_signal_strength": 0.2,
            "asset_config_default": {
                "min_signal_strength_adjustment": 0.0,
                "stop_loss_adjustment": 1.0,
                "position_size_multiplier": 1.0,
            },
            "asset_configs": {},
            "min_position_size_by_pair": {"DOGE/USDT": 1.0},
        }
    )

    result = agent.execute(
        {
            "market_data": {"DOGE/USDT": {"current_price": 0.2}},
            "analysis": {
                "DOGE/USDT": {
                    "signal_strength": 0.8,
                    "volatility_approved": True,
                    "entry_timing_approved": True,
                    "regime": "bullish",
                }
            },
            "backtest_results": {"DOGE/USDT": {"win_rate": 0.6}},
        }
    )

    assert result["success"] is True
    assert "DOGE/USDT" in result["data"]["assessments"]


def test_backtester_non_default_pair_uses_default_factor():
    agent = BacktestingAgent(
        {
            "asset_factor_default": {
                "win_rate_multiplier": 1.0,
                "max_drawdown_adjustment": 1.0,
            },
            "asset_performance_factors": {},
        }
    )

    # BUY baseline drawdown with signal_strength=0.5 -> 0.08 * (1 - 0.15) = 0.068
    dd = agent._estimate_max_drawdown("BUY", 0.5, "DOGE/USDT")
    assert round(dd, 6) == 0.068
