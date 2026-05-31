#!/usr/bin/env python3
"""Paper Trade Runner — Rapid simulation against live klines data.

Runs the full strategy pipeline (MarketAnalysis → Regime → WhaleWatch → Backtest → Risk)
bar-by-bar on historical klines, recording paper trades to a persistent ledger.

This lets you test edge with hundreds of cycles in minutes instead of waiting
hours for live cycles.

Usage:
    # Run 200 1h bars (last ~8 days) with $10,000 simulated balance
    python scripts/paper_trade_runner.py

    # Custom config
    python scripts/paper_trade_runner.py --pairs SOL/USDT,BTC/USDT --balance 5000 --bars 500 --interval 5min

    # Reset ledger and start fresh
    python scripts/paper_trade_runner.py --reset
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.trading.paper_trade_ledger import PaperTradeLedger
from src.intelligence.market_analyzer import MarketAnalysisAgent
from src.intelligence.backtester import BacktestingAgent
from src.intelligence.regime_detector import RegimeDetector
from src.intelligence.whale_watch import WhaleWatch
from src.risk.risk_manager import RiskManagementAgent
from src.data.kucoin_klines_fetcher import KuCoinKlinesFetcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("paper_runner")


def parse_args():
    parser = argparse.ArgumentParser(description="Paper Trade Runner — Rapid simulation with live klines")
    parser.add_argument(
        "--pairs",
        default="SOL/USDT,BTC/USDT,ETH/USDT",
        help="Comma-separated trading pairs (default: SOL/USDT,BTC/USDT,ETH/USDT)",
    )
    parser.add_argument(
        "--balance",
        type=float,
        default=10000.0,
        help="Simulated account balance in USDT (default: 10000)",
    )
    parser.add_argument(
        "--risk-pct",
        type=float,
        default=0.01,
        help="Risk per trade as fraction of balance (default: 0.01 = 1%%)",
    )
    parser.add_argument(
        "--bars",
        type=int,
        default=200,
        help="Number of historical bars to process (default: 200)",
    )
    parser.add_argument(
        "--interval",
        default="1hour",
        help="Klines interval (default: 1hour). Options: 1min,5min,15min,30min,1hour,6hour,1day",
    )
    parser.add_argument(
        "--ledger",
        default="paper_trades_ledger.json",
        help="Ledger file path (default: paper_trades_ledger.json)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset ledger before running (start fresh)",
    )
    parser.add_argument(
        "--min-signal",
        type=float,
        default=0.45,
        help="Minimum signal_strength for trade entry (default: 0.45)",
    )
    parser.add_argument(
        "--min-win-rate",
        type=float,
        default=0.45,
        help="Minimum backtest win rate for trade approval (default: 0.45)",
    )
    parser.add_argument(
        "--stop-loss-pct",
        type=float,
        default=0.04,
        help="Stop loss percentage (default: 0.04 = 4%%)",
    )
    parser.add_argument(
        "--take-profit-ratio",
        type=float,
        default=1.2,
        help="Risk:reward ratio for take profit (default: 1.2)",
    )
    parser.add_argument(
        "--max-open",
        type=int,
        default=10,
        help="Maximum simultaneous open positions (default: 10)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-bar details",
    )
    return parser.parse_args()


def create_exchange_adapter():
    try:
        from src.execution.exchange_adapter import KuCoinAdapter

        api_key = os.getenv("KUCOIN_API_KEY", "dummy")
        api_secret = os.getenv("KUCOIN_API_SECRET", "dummy")
        passphrase = os.getenv("KUCOIN_API_PASSPHRASE", "dummy")
        adapter = KuCoinAdapter(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
        )
        return adapter
    except Exception as e:
        logger.warning(f"KuCoinAdapter creation failed: {e}, using PublicKlinesAdapter")
        return PublicKlinesAdapter()


class PublicKlinesAdapter:
    """Public-only KuCoin adapter that fetches klines via direct HTTP (no SDK, no auth)."""

    BASE_URL = "https://api.kucoin.com"

    def __init__(self):
        self.exchange_name = "kucoin-public"

    @staticmethod
    def _format_symbol(pair: str) -> str:
        return pair.replace("/", "-")

    def get_klines(self, symbol, interval="5min", start=None, end=None):
        import requests as _requests

        kucoin_symbol = self._format_symbol(symbol)
        url = f"{self.BASE_URL}/api/v1/market/candles"
        params = {"symbol": kucoin_symbol, "type": interval}
        if start:
            params["startAt"] = int(start)
        if end:
            params["endAt"] = int(end)

        try:
            resp = _requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") == "200000":
                return body.get("data", [])
            logger.warning(f"KuCoin API error for {kucoin_symbol}: {body.get('msg', 'unknown')}")
            return []
        except Exception as e:
            logger.warning(f"Public klines fetch failed for {kucoin_symbol}: {e}")
            return []


def run_simulation(args):
    pairs = [p.strip() for p in args.pairs.split(",")]

    logger.info(f"Paper Trade Simulation Starting")
    logger.info(f"  Pairs: {pairs}")
    logger.info(f"  Balance: ${args.balance:,.2f}")
    logger.info(f"  Risk/trade: {args.risk_pct:.1%}")
    logger.info(f"  Bars: {args.bars} @ {args.interval}")
    logger.info(f"  Min signal: {args.min_signal}")
    logger.info(f"  Min win rate: {args.min_win_rate:.1%}")

    ledger = PaperTradeLedger(filepath=args.ledger, initial_balance=args.balance)
    if args.reset:
        ledger.reset()
        logger.info("Ledger reset — starting fresh")

    adapter = create_exchange_adapter()
    klines_fetcher = KuCoinKlinesFetcher(
        default_interval=args.interval,
        default_candle_count=args.bars,
        cache_enabled=False,
    )

    if adapter is None:
        logger.error("No exchange adapter available — cannot fetch klines. Exiting.")
        return

    logger.info(f"Fetching {args.bars} {args.interval} klines for {len(pairs)} pairs...")
    klines_data = klines_fetcher.fetch_klines_multi(adapter, pairs, args.interval, args.bars)

    for pair, df in klines_data.items():
        logger.info(f"  {pair}: {len(df)} bars loaded ({df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]})")

    if not klines_data:
        logger.error("No klines data fetched — cannot run simulation")
        return

    regime_detector = RegimeDetector(adx_trend_threshold=20)
    whale_watch = WhaleWatch()
    market_analyzer = MarketAnalysisAgent(config={
        "account_balance": args.balance,
    })
    backtester = BacktestingAgent(config={
        "account_balance": args.balance,
        "min_win_rate": args.min_win_rate,
    })
    backtester.set_klines_infrastructure(klines_fetcher, adapter)

    risk_manager = RiskManagementAgent(config={
        "account_balance": args.balance,
        "risk_per_trade": args.risk_pct,
        "min_signal_strength": args.min_signal,
        "min_win_rate": args.min_win_rate,
        "default_stop_loss_pct": args.stop_loss_pct,
        "min_risk_reward_ratio": args.take_profit_ratio,
        "enforce_min_position_size_only": False,
        "min_notional_usd": 1.0,
    })

    min_bars = min(len(df) for df in klines_data.values()) if klines_data else 0
    warmup = 30
    total_bars = min(min_bars, args.bars)

    logger.info(f"Running simulation: {total_bars - warmup} bars (skipping {warmup} warmup)")

    running_balance = args.balance
    trade_count = 0
    cycle_count = 0

    for bar_idx in range(warmup, total_bars):
        cycle_count += 1
        cycle_trades = 0

        current_prices = {}
        for pair, df in klines_data.items():
            if bar_idx < len(df):
                current_prices[pair] = float(df.iloc[bar_idx]["close"])

        closed = ledger.monitor_open_positions(current_prices)
        for ct in closed:
            running_balance += ct["net_pnl_usd"]
            if args.verbose:
                logger.info(f"  [BAR {bar_idx}] Closed trade #{ct['trade_id']}: ${ct['net_pnl_usd']:+.4f}")

        open_trades = ledger.get_open_trades()
        if len(open_trades) >= args.max_open:
            if args.verbose:
                logger.info(f"  [BAR {bar_idx}] Max open positions reached ({len(open_trades)}), skipping")
            continue

        for pair in pairs:
            if pair not in klines_data:
                continue
            df = klines_data[pair]
            if bar_idx >= len(df):
                continue

            historical_df = df.iloc[:bar_idx + 1].copy()
            if len(historical_df) < 30:
                continue

            bar = df.iloc[bar_idx]
            current_price = float(bar["close"])

            lookback = min(24, bar_idx)
            price_24h_ago = float(df.iloc[bar_idx - lookback]["close"])
            price_change_24h_pct = ((current_price - price_24h_ago) / price_24h_ago) * 100

            price_change_1bar_pct = 0.0
            if bar_idx > 0:
                prev_close = float(df.iloc[bar_idx - 1]["close"])
                price_change_1bar_pct = ((current_price - prev_close) / prev_close) * 100

            vol_lookback = min(24, bar_idx + 1)
            volume_24h = float(df.iloc[bar_idx - vol_lookback + 1:bar_idx + 1]["volume"].sum())

            market_data = {
                pair: {
                    "current_price": current_price,
                    "price_change_24h_pct": price_change_24h_pct,
                    "price_change_1bar_pct": price_change_1bar_pct,
                    "volume_24h": volume_24h,
                }
            }

            analysis_result = market_analyzer.execute({"market_data": market_data})
            if not analysis_result.get("success"):
                continue

            analysis_data = analysis_result.get("data", {})
            pair_analysis = analysis_data.get("analysis", {}).get(pair, {})
            signal_strength = pair_analysis.get("signal_strength", 0)
            recommendation = pair_analysis.get("recommendation", "HOLD")
            regime = pair_analysis.get("regime", "unknown")

            regime_result = None
            whale_result = None
            intel_confidence = 0.0
            intel_action = "HOLD"
            intel_multiplier = 1.0

            try:
                regime_result = regime_detector.analyze(historical_df)
                whale_result = whale_watch.analyze_order_flow(historical_df)

                if regime_result and regime_result.get("recommendation") == "HALT_TRADING":
                    intel_action = "HOLD"
                    intel_confidence = regime_result.get("confidence", 0.5)
                    intel_multiplier = 0.5
                elif whale_result and whale_result.get("signal") == "BULLISH_ABSORPTION" and whale_result.get("confidence", 0) > 0.6:
                    intel_action = "BUY"
                    intel_confidence = whale_result["confidence"]
                    intel_multiplier = 1.0
                elif regime_result and regime_result.get("regime") == "TRENDING_UP":
                    intel_action = "BUY"
                    intel_confidence = regime_result.get("confidence", 0.5)
                    intel_multiplier = regime_detector.get_position_multiplier(regime_result)
                elif regime_result and regime_result.get("recommendation") == "REDUCE_SIZE":
                    intel_action = "HOLD"
                    intel_confidence = 0.5
                    intel_multiplier = 0.5
                elif regime_result and regime_result.get("recommendation") == "SHORT_TREND":
                    intel_action = "SELL"
                    intel_confidence = regime_result.get("confidence", 0.5)
                    intel_multiplier = regime_detector.get_position_multiplier(regime_result)
            except Exception as e:
                if args.verbose:
                    logger.debug(f"  Intelligence analysis failed: {e}")

            if intel_action == "EXIT_ALL":
                if args.verbose:
                    logger.info(f"  [BAR {bar_idx}] {pair}: Intelligence EXIT_ALL")
                continue

            if intel_action == "BUY" and intel_confidence > 0.6:
                boost = intel_confidence * intel_multiplier * 0.15
                signal_strength = min(1.0, signal_strength + boost)
                if args.verbose:
                    logger.info(
                        f"  [BAR {bar_idx}] {pair}: Signal boosted {pair_analysis.get('signal_strength', 0):.3f} → {signal_strength:.3f}"
                    )

            if regime_result:
                adx_regime = regime_result.get("regime", "")
                if "TRENDING_UP" in adx_regime:
                    pair_analysis["regime"] = "bullish"
                elif "TRENDING_DOWN" in adx_regime:
                    pair_analysis["regime"] = "bearish"
                elif "RANGING" in adx_regime:
                    pair_analysis["regime"] = "sideways"
                pair_analysis["atr_pct"] = regime_result.get("atr_pct", 0)

            adx_regime_raw = regime_result.get("regime", "") if regime_result else ""
            adx_value = regime_result.get("adx", 0) if regime_result else 0
            adx_confidence = regime_result.get("confidence", 0) if regime_result else 0

            if adx_regime_raw in ("RANGING_HIGH_VOL", "RANGING_LOW_VOL", "UNKNOWN"):
                if args.verbose:
                    logger.info(f"  [BAR {bar_idx}] {pair}: SKIP — ranging market (ADX={adx_value:.1f}, {adx_regime_raw})")
                continue
            if adx_regime_raw == "TRENDING_DOWN" and recommendation == "BUY":
                if args.verbose:
                    logger.info(f"  [BAR {bar_idx}] {pair}: SKIP — BUY in TRENDING_DOWN (ADX={adx_value:.1f})")
                continue
            if adx_regime_raw == "TRENDING_UP" and recommendation == "SELL":
                if args.verbose:
                    logger.info(f"  [BAR {bar_idx}] {pair}: SKIP — SELL in TRENDING_UP (ADX={adx_value:.1f})")
                continue

            if adx_regime_raw == "TRENDING_DOWN" and recommendation == "HOLD":
                recommendation = "SELL"
                signal_strength = max(signal_strength, adx_confidence * 0.7, 0.50)
                pair_analysis["recommendation"] = recommendation
                pair_analysis["signal_strength"] = signal_strength
                if args.verbose:
                    logger.info(
                        f"  [BAR {bar_idx}] {pair}: TREND SHORT — ADX downtrend override "
                        f"(ADX={adx_value:.1f}, confidence={adx_confidence:.2f}) "
                        f"signal_strength={signal_strength:.3f}"
                    )

            if adx_regime_raw == "TRENDING_UP" and recommendation == "HOLD":
                recommendation = "BUY"
                signal_strength = max(signal_strength, adx_confidence * 0.7, 0.50)
                pair_analysis["recommendation"] = recommendation
                pair_analysis["signal_strength"] = signal_strength
                if args.verbose:
                    logger.info(
                        f"  [BAR {bar_idx}] {pair}: TREND LONG — ADX uptrend override "
                        f"(ADX={adx_value:.1f}, confidence={adx_confidence:.2f}) "
                        f"signal_strength={signal_strength:.3f}"
                    )

            if recommendation == "HOLD":
                continue

            backtest_input = {
                "market_data": market_data,
                "analysis": {pair: pair_analysis},
            }
            backtest_result = backtester.execute(backtest_input)
            if not backtest_result.get("success"):
                continue

            pair_backtest = backtest_result.get("data", {}).get("backtest_results", {}).get(pair, {})
            backtest_win_rate = pair_backtest.get("win_rate", 0.5)

            risk_input = {
                "market_data": market_data,
                "analysis": {pair: pair_analysis},
                "backtest_results": {pair: pair_backtest},
            }

            risk_manager.update_account_balance(running_balance)
            risk_result = risk_manager.execute(risk_input)
            if not risk_result.get("success"):
                continue

            risk_data = risk_result.get("data", {})
            position_approved = risk_data.get("position_approved", False)
            position_size = risk_data.get("position_size", 0)
            stop_loss = risk_data.get("stop_loss", 0)
            take_profit = risk_data.get("take_profit", 0)

            if not position_approved or position_size <= 0:
                if args.verbose:
                    reason = risk_data.get("rejection_reason", "unknown")
                    logger.info(f"  [BAR {bar_idx}] {pair}: REJECTED — {reason}")
                continue

            direction = "long" if recommendation == "BUY" else "short"
            trade_id = ledger.open_trade(
                pair=pair,
                direction=direction,
                entry_price=current_price,
                position_size=position_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
                signal_strength=signal_strength,
                regime=regime,
                intelligence_confidence=intel_confidence,
                intelligence_action=intel_action,
                backtest_win_rate=backtest_win_rate,
                backtest_data_source=pair_backtest.get("data_source", "formula"),
                metadata={
                    "bar_index": bar_idx,
                    "timestamp": str(df.iloc[bar_idx].get("timestamp", "")),
                    "intel_regime": regime_result.get("regime", "") if regime_result else "",
                    "intel_whale": whale_result.get("signal", "") if whale_result else "",
                    "adx": regime_result.get("adx", 0) if regime_result else 0,
                },
            )
            trade_count += 1
            cycle_trades += 1

            if args.verbose or cycle_trades > 0:
                logger.info(
                    f"  [BAR {bar_idx}] {pair}: OPEN #{trade_id} {direction} "
                    f"@ {current_price:.4f} | Size: {position_size:.6f} | "
                    f"Signal: {signal_strength:.3f} | SL: {stop_loss:.4f} | TP: {take_profit:.4f}"
                )

        if cycle_count % 20 == 0:
            stats = ledger.get_statistics()
            logger.info(
                f"  [PROGRESS] Bar {bar_idx}/{total_bars} | "
                f"Balance: ${running_balance:.2f} | "
                f"Trades: {stats['total_trades']} | "
                f"WR: {stats['win_rate']:.1%} | "
                f"P&L: ${stats['total_pnl_usd']:.4f}"
            )

    final_prices = {}
    for pair, df in klines_data.items():
        if len(df) > 0:
            final_prices[pair] = float(df.iloc[-1]["close"])

    open_trades = ledger.get_open_trades()
    if open_trades:
        logger.info(f"Force-closing {len(open_trades)} remaining open positions at final bar prices...")
        for ct in ledger.force_close_all(final_prices, reason="end_of_simulation"):
            running_balance += ct["net_pnl_usd"]

    report = ledger.generate_report()
    print("\n" + report)

    report_path = args.ledger.replace(".json", "_report.txt")
    with open(report_path, "w") as f:
        f.write(report)
    logger.info(f"Report saved to {report_path}")

    sim_config = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pairs": pairs,
        "starting_balance": args.balance,
        "final_balance": running_balance,
        "risk_per_trade": args.risk_pct,
        "bars_processed": total_bars - warmup,
        "interval": args.interval,
        "total_trades_opened": trade_count,
    }
    config_path = args.ledger.replace(".json", "_sim_config.json")
    with open(config_path, "w") as f:
        json.dump(sim_config, f, indent=2)

    logger.info(f"Final balance: ${running_balance:.2f} (started with ${args.balance:,.2f})")

    return ledger


if __name__ == "__main__":
    args = parse_args()
    run_simulation(args)
