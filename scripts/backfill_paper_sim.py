#!/usr/bin/env python3
"""Backfill Paper Simulation — Replay historical date ranges through the strategy pipeline.

Extends paper_trade_runner.py with:
  - Date-range specification (--start-date, --end-date)
  - Paginated kline fetching (KuCoin max 1500 candles/request)
  - Historical timestamp injection (entry_time = bar timestamp, not datetime.now())
  - Incremental append mode (--append to add to existing ledger)
  - Multi-timeframe support (--timeframes for cross-TF edge comparison)

Usage:
  # Backfill last 30 days on 1hour candles
  python scripts/backfill_paper_sim.py --start-date 2026-05-11 --end-date 2026-06-11

  # Backfill specific date range with custom pairs and balance
  python scripts/backfill_paper_sim.py --start-date 2026-04-01 --end-date 2026-05-01 \
      --pairs SOL/USDT,BTC/USDT --balance 5000

  # Append to existing ledger (don't reset)
  python scripts/backfill_paper_sim.py --start-date 2026-05-01 --end-date 2026-06-01 --append

  # Multi-timeframe comparison
  python scripts/backfill_paper_sim.py --start-date 2026-05-01 --end-date 2026-06-01 \
      --timeframes 1hour,4hour,1day
"""

import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.trading.paper_trade_ledger import PaperTradeLedger
from src.config import SPOT_LONG_ONLY
from src.utils.timeframe import get_bars_per_day
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
logger = logging.getLogger("backfill")

KUCOIN_MAX_CANDLES_PER_REQUEST = 1500

INTERVAL_SECONDS = {
    "1min": 60,
    "3min": 180,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1hour": 3600,
    "2hour": 7200,
    "4hour": 14400,
    "6hour": 21600,
    "8hour": 28800,
    "12hour": 43200,
    "1day": 86400,
    "1week": 604800,
}


class BackfillLedger(PaperTradeLedger):
    """PaperTradeLedger subclass that injects historical timestamps instead of datetime.now()."""

    def __init__(self, filepath: str = "paper_trades_ledger.json", initial_balance: float = 10000.0):
        self._simulated_time: Optional[datetime] = None
        super().__init__(filepath=filepath, initial_balance=initial_balance)

    def set_simulated_time(self, dt: Optional[datetime]) -> None:
        self._simulated_time = dt

    def open_trade(
        self,
        pair: str,
        direction: str,
        entry_price: float,
        position_size: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        signal_strength: float = 0.0,
        regime: str = "",
        intelligence_confidence: float = 0.0,
        intelligence_action: str = "",
        backtest_win_rate: float = 0.0,
        backtest_data_source: str = "",
        metadata: Optional[Dict] = None,
    ) -> int:
        import time as _time

        trade_id = self._next_id
        self._next_id += 1

        if self._simulated_time:
            entry_time_str = self._simulated_time.isoformat()
            entry_ts = self._simulated_time.timestamp()
        else:
            entry_time_str = datetime.now(timezone.utc).isoformat()
            entry_ts = _time.time()

        trade = {
            "trade_id": trade_id,
            "pair": pair,
            "direction": direction,
            "entry_price": entry_price,
            "position_size": position_size,
            "entry_value_usd": entry_price * position_size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_time": entry_time_str,
            "entry_timestamp": entry_ts,
            "status": "OPEN",
            "paper_trading": True,
            "signal_strength": signal_strength,
            "regime_at_entry": regime,
            "intelligence_confidence": intelligence_confidence,
            "intelligence_action": intelligence_action,
            "backtest_win_rate": backtest_win_rate,
            "backtest_data_source": backtest_data_source,
            "exit_price": None,
            "exit_time": None,
            "exit_reason": None,
            "pnl_usd": 0.0,
            "pnl_pct": 0.0,
            "fees_usd": 0.0,
            "net_pnl_usd": 0.0,
            "hold_duration_seconds": 0,
            "metadata": metadata or {},
            "backfill": True,
        }

        self.trades.append(trade)
        self._save()
        logger.info(
            f"[LEDGER] Trade #{trade_id} OPENED (backfill): {direction} {pair} "
            f"@ {entry_price:.4f} | Size: {position_size:.6f} | "
            f"SL: {stop_loss:.4f} | TP: {take_profit:.4f} | "
            f"Signal: {signal_strength:.3f}"
        )
        return trade_id


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


def fetch_paginated_klines(
    adapter,
    pair: str,
    interval: str,
    start_ts: int,
    end_ts: int,
) -> "pd.DataFrame":
    """Fetch klines with pagination for date ranges exceeding 1500 candles.

    KuCoin returns max 1500 candles per request. This function paginates
    through the date range, fetching chunks and concatenating them.
    """
    import pandas as pd

    interval_secs = INTERVAL_SECONDS.get(interval, 300)
    max_range_secs = KUCOIN_MAX_CANDLES_PER_REQUEST * interval_secs

    all_raw = []
    current_start = start_ts

    while current_start < end_ts:
        current_end = min(current_start + max_range_secs, end_ts)
        raw = adapter.get_klines(pair, interval, start=current_start, end=current_end)

        if raw:
            all_raw.extend(raw)
            logger.info(
                f"  Fetched {len(raw)} candles for {pair} ({interval}): "
                f"{datetime.fromtimestamp(current_start, tz=timezone.utc).strftime('%Y-%m-%d')} → "
                f"{datetime.fromtimestamp(current_end, tz=timezone.utc).strftime('%Y-%m-%d')}"
            )

        current_start = current_end
        time.sleep(1.1)

    df = KuCoinKlinesFetcher.raw_klines_to_dataframe(all_raw)

    if not df.empty:
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    return df


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backfill Paper Simulation — Replay historical date ranges through the strategy pipeline"
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Start date for backfill (YYYY-MM-DD, UTC)",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date for backfill (YYYY-MM-DD, UTC). Default: now",
    )
    parser.add_argument(
        "--pairs",
        default="BTC/USDT,ETH/USDT",
        help="Comma-separated trading pairs (default: BTC/USDT,ETH/USDT)",
    )
    parser.add_argument(
        "--balance",
        type=float,
        default=110.0,
        help="Simulated account balance in USDT (default: 110)",
    )
    parser.add_argument(
        "--risk-pct",
        type=float,
        default=0.02,
        help="Risk per trade as fraction of balance (default: 0.02 = 2%%)",
    )
    parser.add_argument(
        "--interval",
        default="1hour",
        help="Primary kline interval (default: 1hour). Used when --timeframes is not set.",
    )
    parser.add_argument(
        "--timeframes",
        default=None,
        help="Comma-separated timeframes to test (default: None, uses --interval). "
             "Example: 1hour,4hour,1day — runs a separate simulation per TF.",
    )
    parser.add_argument(
        "--ledger",
        default="paper_trades_ledger.json",
        help="Ledger file path (default: paper_trades_ledger.json)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing ledger (default: reset ledger before backfill)",
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


def run_single_timeframe(
    args,
    interval: str,
    pairs: list,
    start_ts: int,
    end_ts: int,
    spot_long_only: bool,
    ledger_suffix: str = "",
) -> "BackfillLedger":
    """Run the full bar-by-bar simulation for a single timeframe."""

    ledger_path = args.ledger.replace(".json", f"{ledger_suffix}.json") if ledger_suffix else args.ledger
    ledger = BackfillLedger(filepath=ledger_path, initial_balance=args.balance)
    if not args.append:
        ledger.reset()
        logger.info(f"Ledger reset — starting fresh ({ledger_path})")

    adapter = PublicKlinesAdapter()

    logger.info(f"Fetching paginated klines for {len(pairs)} pairs @ {interval}...")
    klines_data = {}
    for pair in pairs:
        df = fetch_paginated_klines(adapter, pair, interval, start_ts, end_ts)
        if not df.empty:
            klines_data[pair] = df
            logger.info(f"  {pair}: {len(df)} bars ({df['timestamp'].iloc[0]} → {df['timestamp'].iloc[-1]})")
        else:
            logger.warning(f"  {pair}: no klines data returned")

    if not klines_data:
        logger.error("No klines data fetched — cannot run backfill")
        return ledger

    regime_detector = RegimeDetector(adx_trend_threshold=20, timeframe=interval)
    whale_watch = WhaleWatch()
    market_analyzer = MarketAnalysisAgent(config={
        "account_balance": args.balance,
        "timeframe": interval,
    })

    klines_fetcher = KuCoinKlinesFetcher(
        default_interval=interval,
        default_candle_count=200,
        cache_enabled=False,
    )
    backtester = BacktestingAgent(config={
        "account_balance": args.balance,
        "min_win_rate": args.min_win_rate,
        "timeframe": interval,
    })
    backtester.set_klines_infrastructure(klines_fetcher, adapter)

    risk_manager = RiskManagementAgent(config={
        "account_balance": args.balance,
        "risk_per_trade": args.risk_pct,
        "timeframe": interval,
        "min_signal_strength": args.min_signal,
        "min_win_rate": args.min_win_rate,
        "default_stop_loss_pct": args.stop_loss_pct,
        "min_risk_reward_ratio": args.take_profit_ratio,
        "enforce_min_position_size_only": False,
        "min_notional_usd": 10.0,
    })

    min_bars = min(len(df) for df in klines_data.values()) if klines_data else 0
    warmup = 30
    total_bars = min_bars

    if total_bars <= warmup:
        logger.error(f"Not enough bars for simulation: {total_bars} total, {warmup} warmup needed")
        return ledger

    logger.info(
        f"Running backfill simulation [{interval}]: "
        f"{total_bars - warmup} bars (skipping {warmup} warmup) across {len(pairs)} pairs"
    )

    running_balance = args.balance
    trade_count = 0
    cycle_count = 0

    for bar_idx in range(warmup, total_bars):
        cycle_count += 1
        cycle_trades = 0

        current_prices = {}
        bar_timestamp = None
        for pair, df in klines_data.items():
            if bar_idx < len(df):
                current_prices[pair] = float(df.iloc[bar_idx]["close"])
                if bar_timestamp is None:
                    bar_timestamp = df.iloc[bar_idx]["timestamp"]

        if bar_timestamp is not None:
            if hasattr(bar_timestamp, "to_pydatetime"):
                ledger.set_simulated_time(bar_timestamp.to_pydatetime())
            elif isinstance(bar_timestamp, datetime):
                ledger.set_simulated_time(bar_timestamp)
            else:
                ledger.set_simulated_time(None)
        else:
            ledger.set_simulated_time(None)

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

            lookback = min(get_bars_per_day(interval), bar_idx)
            price_24h_ago = float(df.iloc[bar_idx - lookback]["close"])
            price_change_24h_pct = ((current_price - price_24h_ago) / price_24h_ago) * 100

            price_change_1bar_pct = 0.0
            if bar_idx > 0:
                prev_close = float(df.iloc[bar_idx - 1]["close"])
                price_change_1bar_pct = ((current_price - prev_close) / prev_close) * 100

            vol_lookback = min(get_bars_per_day(interval), bar_idx + 1)
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
            except Exception as e:
                if args.verbose:
                    logger.debug(f"  Intelligence analysis failed: {e}")

            if regime_result and regime_result.get("recommendation") == "SHORT_TREND":
                if spot_long_only:
                    intel_action = "HOLD"
                    intel_confidence = regime_result.get("confidence", 0.5)
                    intel_multiplier = 0.0
                else:
                    intel_action = "SELL"
                    intel_confidence = regime_result.get("confidence", 0.5)
                    intel_multiplier = regime_detector.get_position_multiplier(regime_result)

            if intel_action == "EXIT_ALL":
                if args.verbose:
                    logger.info(f"  [BAR {bar_idx}] {pair}: Intelligence EXIT_ALL")
                continue

            if intel_action == "BUY" and intel_confidence > 0.6:
                boost = intel_confidence * intel_multiplier * 0.15
                signal_strength = min(1.0, signal_strength + boost)

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
                if spot_long_only:
                    recommendation = "HOLD"
                else:
                    recommendation = "SELL"
                signal_strength = max(signal_strength, adx_confidence * 0.7, 0.50)
                pair_analysis["recommendation"] = recommendation
                pair_analysis["signal_strength"] = signal_strength

            if adx_regime_raw == "TRENDING_UP" and recommendation == "HOLD":
                recommendation = "BUY"
                signal_strength = max(signal_strength, adx_confidence * 0.7, 0.50)
                pair_analysis["recommendation"] = recommendation
                pair_analysis["signal_strength"] = signal_strength

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
            if spot_long_only and recommendation == "SELL":
                continue
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

            direction = "long" if (recommendation == "BUY" or spot_long_only) else "short"
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
                    "backfill_interval": interval,
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

        if cycle_count % 50 == 0:
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
        for ct in ledger.force_close_all(final_prices, reason="end_of_backfill"):
            running_balance += ct["net_pnl_usd"]

    report = ledger.generate_report()
    print(f"\n{'='*60}")
    print(f"  BACKFILL REPORT [{interval}]")
    print(f"{'='*60}")
    print(report)

    report_path = ledger_path.replace(".json", "_report.txt")
    with open(report_path, "w") as f:
        f.write(report)
    logger.info(f"Report saved to {report_path}")

    sim_config = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "backfill",
        "start_date": args.start_date,
        "end_date": args.end_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "pairs": pairs,
        "starting_balance": args.balance,
        "final_balance": running_balance,
        "risk_per_trade": args.risk_pct,
        "bars_processed": total_bars - warmup,
        "interval": interval,
        "total_trades_opened": trade_count,
    }
    config_path = ledger_path.replace(".json", "_sim_config.json")
    with open(config_path, "w") as f:
        json.dump(sim_config, f, indent=2)

    logger.info(f"Final balance [{interval}]: ${running_balance:.2f} (started with ${args.balance:,.2f})")
    logger.info(f"Config saved to {config_path}")

    ledger.set_simulated_time(None)
    return ledger


def main():
    args = parse_args()
    pairs = [p.strip() for p in args.pairs.split(",")]
    spot_long_only = SPOT_LONG_ONLY

    try:
        start_dt = datetime.strptime(args.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        logger.error(f"Invalid start-date format: {args.start_date}. Use YYYY-MM-DD.")
        sys.exit(1)

    if args.end_date:
        try:
            end_dt = datetime.strptime(args.end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        except ValueError:
            logger.error(f"Invalid end-date format: {args.end_date}. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        end_dt = datetime.now(timezone.utc)

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    if start_ts >= end_ts:
        logger.error(f"Start date must be before end date: {args.start_date} >= {args.end_date or 'now'}")
        sys.exit(1)

    logger.info(f"Backfill Paper Simulation")
    logger.info(f"  Date range: {start_dt.strftime('%Y-%m-%d')} → {end_dt.strftime('%Y-%m-%d')}")
    logger.info(f"  Pairs: {pairs}")
    logger.info(f"  Balance: ${args.balance:,.2f}")
    logger.info(f"  Risk/trade: {args.risk_pct:.1%}")
    logger.info(f"  Min signal: {args.min_signal}")
    logger.info(f"  Min win rate: {args.min_win_rate:.1%}")
    logger.info(f"  Append mode: {args.append}")

    if args.timeframes:
        timeframes = [tf.strip() for tf in args.timeframes.split(",")]
        logger.info(f"  Timeframes: {timeframes}")

        results = {}
        for tf in timeframes:
            logger.info(f"\n{'='*60}")
            logger.info(f"  Starting timeframe: {tf}")
            logger.info(f"{'='*60}")
            suffix = f"_{tf}"
            ledger = run_single_timeframe(
                args, tf, pairs, start_ts, end_ts, spot_long_only, ledger_suffix=suffix
            )
            stats = ledger.get_statistics()
            results[tf] = {
                "total_trades": stats["total_trades"],
                "win_rate": stats["win_rate"],
                "total_pnl_usd": stats["total_pnl_usd"],
                "final_balance": stats.get("final_balance", args.balance + stats["total_pnl_usd"]),
            }

        print(f"\n{'='*60}")
        print(f"  CROSS-TIMEFRAME COMPARISON")
        print(f"{'='*60}")
        print(f"  {'TF':<10} {'Trades':>8} {'Win Rate':>10} {'P&L (USD)':>12} {'Balance':>12}")
        print(f"  {'-'*10} {'-'*8} {'-'*10} {'-'*12} {'-'*12}")
        for tf, r in results.items():
            print(
                f"  {tf:<10} {r['total_trades']:>8} {r['win_rate']:>9.1%} "
                f"{r['total_pnl_usd']:>+12.4f} {r['final_balance']:>12.2f}"
            )
    else:
        run_single_timeframe(args, args.interval, pairs, start_ts, end_ts, spot_long_only)


if __name__ == "__main__":
    main()
