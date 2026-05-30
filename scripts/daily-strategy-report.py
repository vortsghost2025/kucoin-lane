#!/usr/bin/env python3
"""
Daily Strategy Validation Report
=================================
One-command health check for the trading strategy pipeline.

Run inside container:
  docker exec kucoin-lane python /app/scripts/daily-strategy-report.py

Run standalone:
  python scripts/daily-strategy-report.py

Reports: regime, signals, win rates, risk decisions, drift indicators.
No real orders placed. Read-only + paper execution only.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
IN_CONTAINER = Path("/app/src").exists()

if IN_CONTAINER:
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
else:
    if str(REPO_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "src"))
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

IMPORT_PREFIX = "src." if IN_CONTAINER else ""

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / "config" / ".env")
    load_dotenv(Path("/app/config/.env"))
except ImportError:
    pass

logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
logger = logging.getLogger("strategy-report")


def run_report():
    report = {
        "report_type": "daily_strategy_validation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pairs": [],
        "summary": {},
    }

    pairs_str = os.getenv("TRADING_PAIRS", "SOL/USDT,BTC/USDT,ETH/USDT")
    pairs = [p.strip() for p in pairs_str.split(",") if p.strip()]
    account_balance = float(os.getenv("ACCOUNT_BALANCE", "80"))

    config = {
        "paper_trading": True,
        "paper_live": True,
        "account_balance": account_balance,
        "trading_pairs": pairs,
    }

    # Stage 1: Fetch live data
    try:
        DataFetchingAgent = __import__(
            f"{IMPORT_PREFIX}data.data_fetcher", fromlist=["DataFetchingAgent"]
        ).DataFetchingAgent

        dfa = DataFetchingAgent(config)
        fetch_result = dfa.execute({"symbols": pairs})
        if not fetch_result.get("success"):
            report["error"] = f"Data fetch failed: {fetch_result}"
            print(json.dumps(report, indent=2))
            return 1
        market_data = fetch_result.get("data", {}).get("market_data", {})
    except Exception as e:
        report["error"] = f"Data fetch error: {e}"
        print(json.dumps(report, indent=2))
        return 1

    # Stage 2: Market analysis
    analysis_data = {}
    try:
        MarketAnalysisAgent = __import__(
            f"{IMPORT_PREFIX}intelligence.market_analyzer", fromlist=["MarketAnalysisAgent"]
        ).MarketAnalysisAgent

        maa = MarketAnalysisAgent(config)
        analysis_result = maa.execute({"market_data": market_data})
        analysis_data = analysis_result.get("data", {}) if analysis_result.get("success") else {}
    except Exception as e:
        logger.warning(f"Market analysis error: {e}")

    # Stage 3: Backtesting
    backtest_data = {}
    try:
        BacktestingAgent = __import__(
            f"{IMPORT_PREFIX}intelligence.backtester", fromlist=["BacktestingAgent"]
        ).BacktestingAgent

        ba = BacktestingAgent(config)
        bt_result = ba.execute(
            {
                "market_data": market_data,
                "analysis": analysis_data.get("analysis", {}),
            },
        )
        backtest_data = bt_result.get("data", {}) if bt_result.get("success") else {}
    except Exception as e:
        logger.warning(f"Backtest error: {e}")

    # Stage 4: Risk assessment
    try:
        RiskManagementAgent = __import__(
            f"{IMPORT_PREFIX}risk.risk_manager", fromlist=["RiskManagementAgent"]
        ).RiskManagementAgent

        rma = RiskManagementAgent(config)
        risk_result = rma.execute(
            {
                "market_data": market_data,
                "analysis": analysis_data.get("analysis", {}),
                "backtest_results": backtest_data.get("backtest_results", {}),
            },
        )
        risk_data = risk_result.get("data", {}) if risk_result.get("success") else {}
    except Exception as e:
        risk_data = {"error": str(e)}
        logger.warning(f"Risk assessment error: {e}")

    # Build per-pair report
    approved_count = 0
    rejected_count = 0

    risk_assessments = risk_data.get("assessments", {})

    for pair in pairs:
        pair_info = {
            "pair": pair,
            "price": None,
            "regime": None,
            "signal": None,
            "recommendation": None,
            "win_rate": None,
            "position_approved": None,
            "position_size": None,
            "rejection_reason": None,
        }

        # Price
        md = market_data.get(pair, {})
        if isinstance(md, dict):
            pair_info["price"] = md.get("current_price")

        # Analysis
        an = analysis_data.get("analysis", {}).get(pair, {})
        if isinstance(an, dict):
            pair_info["regime"] = an.get("regime", analysis_data.get("regime"))
            pair_info["signal"] = an.get("signal", an.get("signal_strength"))
            pair_info["recommendation"] = an.get("recommendation")

        # Backtest
        bt = backtest_data.get("backtest_results", {}).get(pair, {})
        if isinstance(bt, dict):
            pair_info["win_rate"] = bt.get("win_rate")

        # Risk
        ra = risk_assessments.get(pair, {})
        if isinstance(ra, dict) and ra.get("pair") == pair:
            pair_info["position_approved"] = ra.get("position_approved")
            pair_info["position_size"] = ra.get("position_size")
            pair_info["rejection_reason"] = ra.get("rejection_reason")
        elif isinstance(risk_data, dict) and "error" in risk_data:
            pair_info["rejection_reason"] = f"risk_error: {risk_data['error']}"

        if pair_info["position_approved"]:
            approved_count += 1
        else:
            rejected_count += 1

        report["pairs"].append(pair_info)

    # Overall regime
    report["summary"] = {
        "overall_regime": analysis_data.get("regime", "unknown"),
        "pairs_approved": approved_count,
        "pairs_rejected": rejected_count,
        "total_pairs": len(pairs),
        "account_balance": account_balance,
        "data_source": "live",
        "execution_mode": "paper",
    }

    # Drift indicators
    if approved_count == 0:
        report["drift_indicators"] = {
            "status": "ALL_REJECTED",
            "note": "No pairs approved - signals may be weak or regime unfavorable",
        }
    elif approved_count == len(pairs):
        report["drift_indicators"] = {
            "status": "ALL_APPROVED",
            "note": "All pairs approved - verify risk thresholds not too loose",
        }
    else:
        report["drift_indicators"] = {
            "status": "NORMAL",
            "note": f"{approved_count}/{len(pairs)} pairs approved",
        }

    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(run_report())
