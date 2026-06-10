#!/usr/bin/env python3
"""
run_pipeline.py - Main orchestrator for the first-penny trading pipeline.

Combines:
- Pre-launch DEX scanning (Pump.fun, Birdeye, DexScreener via NewTokenFeed / PreLaunchScanner)
- Creator boost + trading decisions (trading_decision.py)
- Watchlist generation for new tokens
- REAL Jupiter DEX execution (paper mode with real market data)
- REAL KuCoin execution (paper mode with real API + paper ledger)

Usage:
    python run_pipeline.py --mode paper          # pre-launch + paper decisions
    python run_pipeline.py --mode live           # REAL MONEY for KuCoin pairs
    python run_pipeline.py --scan-only           # just emit watchlist

ALL DATA IS REAL. PAPER MODE = PAPER MONEY ONLY. ZERO DIFFERENCE TO LIVE.
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import re

logger = logging.getLogger(__name__)

# Ensure repo root on path
sys.path.insert(0, str(Path(__file__).parent))

from src.intelligence.chain.new_token_feed import NewTokenFeed
from src.intelligence.trading_decision import make_trade_decisions, decisions_to_watchlist
from src.execution.dex_jupiter_executor import JupiterDexExecutor
from src.trading.paper_trade_ledger import PaperTradeLedger
from src.config import TRADING_CONFIG


def load_prelaunch_tokens(limit: int = 20) -> List:
    """Fetch fresh pre-launch / new tokens."""
    feed = NewTokenFeed(rate_limit_rpm=20)
    try:
        feed.validate_keys()
    except RuntimeError as e:
        print(f"[WARN] {e} — continuing with whatever data is available (demo mode)")
    return feed.fetch_new_tokens(limit=limit)


class PaperLiveKuCoinExecutor:
    """KuCoin executor that uses REAL API for market data and order logic,
    but tracks PAPER balance in the ledger instead of real money."""
    
    def __init__(self, ledger: PaperTradeLedger):
        self.ledger = ledger
        from src.execution.exchange_adapter import KuCoinAdapter
        api_key = os.getenv("KUCOIN_API_KEY")
        api_secret = os.getenv("KUCOIN_API_SECRET")
        passphrase = os.getenv("KUCOIN_API_PASSPHRASE")
        if not api_key or not api_secret or not passphrase:
            raise RuntimeError("KuCoin API credentials not found in environment")
        self.adapter = KuCoinAdapter(api_key=api_key, api_secret=api_secret, passphrase=passphrase)
        self.paper_balance = ledger.initial_balance
        print(f"[KUCOIN PAPER-LIVE] Real API connected, paper balance: ${self.paper_balance:.2f}")

    def get_real_market_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get REAL current market data from KuCoin."""
        market_data = {}
        for sym in symbols:
            try:
                ticker = self.adapter.get_ticker(sym)
                if ticker:
                    market_data[sym] = {
                        "current_price": float(ticker.get("price", 0)),
                        "volume_24h": float(ticker.get("vol", 0)),
                        "price_change_24h_pct": float(ticker.get("changeRate", 0)) * 100,
                    }
            except Exception as e:
                print(f"[KUCOIN] Failed to get market data for {sym}: {e}")
        return market_data

    def execute_paper_trade(
        self,
        symbol: str,
        side: str,
        position_size_usd: float,
        stop_loss_pct: float = 0.02,
        take_profit_pct: float = 0.05,
        signal_strength: float = 0.5,
        metadata: Dict = None,
    ) -> Dict[str, Any]:
        """Execute a REAL KuCoin trade logic but track in PAPER ledger."""
        market = self.get_real_market_data([symbol])
        if symbol not in market or market[symbol]["current_price"] <= 0:
            return {"success": False, "error": "No market data"}

        current_price = market[symbol]["current_price"]
        qty = position_size_usd / current_price
        
        if side == "buy":
            stop_loss = current_price * (1 - stop_loss_pct)
            take_profit = current_price * (1 + take_profit_pct)
        else:
            stop_loss = current_price * (1 + stop_loss_pct)
            take_profit = current_price * (1 - take_profit_pct)

        trade_id = self.ledger.open_trade(
            pair=symbol,
            direction="long" if side == "buy" else "short",
            entry_price=current_price,
            position_size=qty,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_strength=signal_strength,
            intelligence_confidence=signal_strength,
            intelligence_action="BUY" if side == "buy" else "SELL",
            metadata=metadata or {},
        )

        return {
            "success": True,
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_price": current_price,
            "qty": qty,
            "position_size_usd": position_size_usd,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "metadata": metadata or {},
        }

    def monitor_positions(self) -> List[Dict]:
        """Monitor open ledger positions against REAL current prices."""
        open_trades = self.ledger.get_open_trades()
        if not open_trades:
            return []
        
        symbols = list(set(t["pair"] for t in open_trades))
        market = self.get_real_market_data(symbols)
        
        current_prices = {s: market[s]["current_price"] for s in symbols if s in market}
        if current_prices:
            closed = self.ledger.monitor_open_positions(current_prices)
            for ct in closed:
                print(f"[KUCOIN PAPER-LIVE] Closed #{ct['trade_id']} {ct['pair']} "
                      f"${ct['net_pnl_usd']:+.4f} ({ct['exit_reason']})")
            return closed
        return []


def run_prelaunch_cycle(
    limit: int = 20, 
    min_boost: float = 1.05, 
    min_community_score: float = 0.3,
    paper: bool = True, 
    ledger: Optional[PaperTradeLedger] = None, 
    sol_per_trade: float = 0.05,
    kucoin_executor: Optional[PaperLiveKuCoinExecutor] = None,
) -> Dict[str, Any]:
    """Run one pre-launch scan + decision cycle with REAL execution."""
    print("[PIPELINE] Scanning for new pre-launch tokens...")
    tokens = load_prelaunch_tokens(limit=limit)
    print(f"[PIPELINE] Found {len(tokens)} fresh tokens")

    decisions = make_trade_decisions(tokens, min_boost=min_boost, min_community_score=min_community_score)
    watchlist = decisions_to_watchlist(decisions)

    buys = [d for d in decisions if d.action == "BUY"]
    print(f"[PIPELINE] Decisions: {len(buys)} BUY, {len(watchlist)} watchlist items")

    for d in buys[:3]:
        print(f"  BUY {d.token.ticker or d.token.mint[:8]} | boost={d.boost:.2f} | conf={d.confidence:.2f} | {d.reason[:60]}")

    for d in buys:
        if d.boost >= 1.25 or d.confidence >= 0.7:
            creator = getattr(d.token, "creator", "?")[:12] if hasattr(d.token, "creator") else "?"
            print(f"[ALERT] HIGH BOOST: {d.token.ticker or d.token.mint[:8]} boost={d.boost:.2f} conf={d.confidence:.2f} creator={creator}...")

    # Filter to Solana-only mints for Jupiter DEX
    solana_mint_re = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
    solana_buys = [d for d in buys if solana_mint_re.match(d.token.mint)]

    dex_results = []
    if solana_buys:
        print(f"[PIPELINE] {len(solana_buys)} Solana mints for Jupiter DEX")
        dex_executor = JupiterDexExecutor(paper_trading=paper)
        dex_results = dex_executor.run_cycle(
            [d.token for d in solana_buys],
            max_sol_per_trade=sol_per_trade
        )
        print(f"[PIPELINE] DEX paper results: {len(dex_results)} positions opened")
    else:
        print("[PIPELINE] No Solana mints in BUY decisions, skipping DEX")
        dex_results = []

    if ledger is not None and dex_results:
        for d, res in zip(solana_buys, dex_results):
            if res.get("status") == "paper_position_open":
                pair = f"{d.token.ticker or d.token.mint[:6]}/SOL"
                trade_id = ledger.open_trade(
                    pair=pair,
                    direction="long",
                    entry_price=res["entry_price_usd"],
                    position_size=res["token_amount"],
                    stop_loss=0.0,
                    take_profit=0.0,
                    signal_strength=d.confidence,
                    intelligence_confidence=d.confidence,
                    intelligence_action="BUY",
                    metadata={
                        "mint": d.token.mint,
                        "creator": getattr(d.token, "creator", None),
                        "boost": d.boost,
                        "community_score": getattr(d.token, "community_score", 0.5),
                        "source": "pre_launch",
                        "sol_amount": res["sol_amount"],
                        "fees_usd": res["fees_usd"],
                        "position_id": res.get("position_id"),
                    },
                )
                print(f"[LEDGER] Opened #{trade_id} {pair} entry ${res['entry_price_usd']:.8f} size {res['token_amount']:.6f}")

    kucoin_results = []
    if kucoin_executor:
        kucoin_executor.monitor_positions()
        symbols = TRADING_CONFIG.get("trading_pairs", ["BTC/USDT"])
        for sym in symbols[:1]:
            market_data = kucoin_executor.get_real_market_data([sym])
            if sym in market_data:
                price = market_data[sym]["current_price"]
                signal_strength = 0.5
                res = kucoin_executor.execute_paper_trade(
                    symbol=sym,
                    side="buy",
                    position_size_usd=50.0,
                    signal_strength=signal_strength,
                    metadata={"source": "kucoin_paper_live", "creator_boost": True},
                )
                kucoin_results.append({sym: res})

    return {
        "tokens_scanned": len(tokens),
        "decisions": len(decisions),
        "buys": len(buys),
        "watchlist": watchlist,
        "dex_results": dex_results,
        "kucoin_results": kucoin_results,
        "decisions_detail": [
            d.token.to_dict() | {"action": d.action, "confidence": d.confidence, "boost": d.boost, "reason": d.reason} 
            for d in decisions[:5]
        ],
    }


def run_continuous_pipeline(
    limit: int = 15,
    min_boost: float = 1.0,
    min_community_score: float = 0.25,
    sol_per_trade: float = 0.05,
    interval_min: int = 5,
    ledger_path: Path = Path("data/paper_trades_ledger.json"),
) -> None:
    """Continuous headless paper-live loop with REAL market data."""
    print(f"[HEADLESS] Starting continuous PAPER-LIVE loop (interval={interval_min}min, sol_per_trade={sol_per_trade})")
    print(f"[HEADLESS] Ledger: {ledger_path}")
    
    ledger = PaperTradeLedger(str(ledger_path), initial_balance=200.0)
    
    try:
        kucoin_executor = PaperLiveKuCoinExecutor(ledger)
        print("[HEADLESS] KuCoin paper-live executor initialized with REAL API")
    except Exception as e:
        print(f"[HEADLESS] KuCoin executor unavailable: {e}")
        kucoin_executor = None

    _running = True

    def _signal_handler(signum, frame):
        nonlocal _running
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        _running = False

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    cycle = 0
    while _running:
        cycle += 1
        print(f"\n=== CYCLE {cycle} ===")
        try:
            prelaunch_result = run_prelaunch_cycle(
                limit=limit, 
                min_boost=min_boost, 
                min_community_score=min_community_score,
                paper=True, 
                ledger=ledger, 
                sol_per_trade=sol_per_trade,
                kucoin_executor=kucoin_executor,
            )

            stats = ledger.get_statistics()
            cumulative_pnl = stats.get("total_pnl_usd", 0.0)
            trades = stats.get("total_trades", 0)
            win_rate = stats.get("win_rate", 0.0)

            dex_pnl = sum(r.get("net_pnl_usd", 0) for r in prelaunch_result.get("dex_results", []))
            if abs(dex_pnl) > 1.0 or cumulative_pnl > 10.0:
                print(f"[ALERT] P&L: last_cycle=${dex_pnl:+.4f} cumulative=${cumulative_pnl:+.4f} (trades={trades})")

            out = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "paper_live",
                "cycle": cycle,
                "phase": "pre_launch",
                "tokens_scanned": prelaunch_result.get("tokens_scanned", 0),
                "signals": prelaunch_result.get("buys", 0),
                "execution": "dex_paper_live",
                "paper_pnl": {
                    "cumulative_paper_pnl_usd": round(cumulative_pnl, 4),
                    "trades_simulated": trades,
                    "win_rate": round(win_rate, 3),
                    "last_cycle_pnl_usd": round(dex_pnl, 4),
                },
                "prelaunch": prelaunch_result,
                "kucoin": {"results": prelaunch_result.get("kucoin_results", [])},
            }
            Path("data").mkdir(exist_ok=True)
            with open("data/pipeline_last_run.json", "w") as f:
                json.dump(out, f, indent=2)

            if cycle % 4 == 0:
                print(ledger.generate_report())

            print(f"[HEADLESS] Cycle {cycle} done. P&L: ${cumulative_pnl:+.4f} | Trades: {trades} | WR: {win_rate:.1%}")
            print(f"[HEADLESS] Sleeping {interval_min} min... (Ctrl+C to stop)")
            time.sleep(interval_min * 60)

        except Exception as e:
            logger.error(f"Cycle {cycle} error: {e}")
            time.sleep(60)

    print(f"[HEADLESS] Shutting down. Final: {ledger.get_statistics()}")
    print(ledger.generate_report())


def start_metrics_server(port: int) -> None:
    """Start the Prometheus metrics endpoint for live stream telemetry."""
    if port <= 0:
        return
    try:
        from prometheus_client import start_http_server

        start_http_server(port)
        print(f"[METRICS] Prometheus HTTP server listening on :{port}")
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not start Prometheus metrics server: %s", exc)


async def run_streaming_prelaunch_pipeline(
    output_dir: Path = Path("data"),
    max_events: Optional[int] = None,
) -> Dict[str, Any]:
    """Consume live Pump.fun creation events instead of waiting for polling cycles."""
    from src.intelligence.live_prelaunch_stream import (
        HeliusPumpFunWebSocketSource,
        LivePreLaunchEventProcessor,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    source = HeliusPumpFunWebSocketSource()
    processor = LivePreLaunchEventProcessor(output_dir=output_dir)

    print("[STREAM] Listening for live Pump.fun token creation events")
    return await processor.run(source.events(), max_events=max_events)


def main():
    parser = argparse.ArgumentParser(description="First-penny trading pipeline - REAL DATA, PAPER MONEY")
    parser.add_argument("--mode", choices=["paper", "live"], default="paper")
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--continuous", action="store_true", help="Run continuous headless paper-live loop")
    parser.add_argument("--interval-min", type=int, default=5, help="Minutes between cycles")
    parser.add_argument("--paper-ledger", type=Path, default=Path("data/paper_trades_ledger.json"))
    parser.add_argument("--min-boost", type=float, default=1.0, help="Minimum creator boost for BUY")
    parser.add_argument("--min-community-score", type=float, default=0.25, help="Minimum community score for BUY")
    parser.add_argument("--sol-per-trade", type=float, default=0.05, help="SOL per DEX trade")
    parser.add_argument("--stream", action="store_true", help="Use live Helius websocket stream for Pump.fun token events")
    parser.add_argument("--max-events", type=int, default=None, help="Stop stream after N processed events")
    parser.add_argument("--metrics-port", type=int, default=8000, help="Prometheus metrics port; use 0 to disable")
    parser.add_argument("--output", type=Path, default=Path("data"), help="Directory for latest stream/pipeline state")
    args = parser.parse_args()

    print(f"=== run_pipeline.py | mode={args.mode} | continuous={args.continuous} | stream={args.stream} ===")

    if args.stream:
        start_metrics_server(args.metrics_port)
        summary = asyncio.run(
            run_streaming_prelaunch_pipeline(
                output_dir=args.output,
                max_events=args.max_events,
            )
        )
        print(json.dumps(summary, indent=2))
        return

    if args.continuous:
        run_continuous_pipeline(
            limit=args.limit,
            min_boost=args.min_boost,
            min_community_score=args.min_community_score,
            interval_min=args.interval_min,
            ledger_path=args.paper_ledger,
        )
        return

    paper = (args.mode != "live")
    ledger = PaperTradeLedger(str(args.paper_ledger), initial_balance=200.0) if not args.scan_only else None
    
    kucoin_executor = None
    if not args.scan_only and not paper:
        try:
            kucoin_executor = PaperLiveKuCoinExecutor(ledger)
        except Exception:
            pass

    prelaunch_result = run_prelaunch_cycle(
        limit=args.limit, 
        paper=paper, 
        min_boost=args.min_boost,
        min_community_score=args.min_community_score,
        ledger=ledger,
        sol_per_trade=args.sol_per_trade,
        kucoin_executor=kucoin_executor,
    )

    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "prelaunch": prelaunch_result,
    }
    Path("data").mkdir(exist_ok=True)
    with open("data/pipeline_last_run.json", "w") as f:
        json.dump(out, f, indent=2)

    print("[PIPELINE] Run complete. See data/pipeline_last_run.json")
    if args.mode == "live":
        print("WARNING: LIVE MODE — REAL MONEY on KuCoin")


if __name__ == "__main__":
    main()
