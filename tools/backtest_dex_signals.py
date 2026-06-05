#!/usr/bin/env python3
"""
DEX Signal Backtester — Validate DEX intelligence signals against historical CEX listings.

Usage:
    python tools/backtest_dex_signals.py --days 30 --chain solana
    python tools/backtest_dex_signals.py --simulate --scan-history data/dex_scan_history.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.dex_intelligence import DexScanner
from src.data.kucoin_klines_fetcher import KuCoinKlinesFetcher
from src.execution.exchange_adapter import KuCoinAdapter

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

HISTORY_FILE = Path("data/dex_scan_history.json")
KUCOIN_LISTINGS_FILE = Path("data/kucoin_listings.json")


class DexSignalBacktester:
    """Backtests DEX signals against subsequent CEX listings and price action."""

    def __init__(self, chain: str = "solana", rpc_url: Optional[str] = None):
        self.chain = chain
        self.scanner = DexScanner(chains=[chain], rpc_url=rpc_url)
        self.klines_fetcher = KuCoinKlinesFetcher(default_interval="1hour", default_candle_count=200)
        
        # Use dummy credentials for public endpoints only
        api_key = os.getenv("KUCOIN_API_KEY", "dummy")
        api_secret = os.getenv("KUCOIN_API_SECRET", "dummy")
        passphrase = os.getenv("KUCOIN_PASSPHRASE", "dummy")
        self.exchange_adapter = KuCoinAdapter(api_key, api_secret, passphrase)

    def run_historical_scans(self, days: int, interval_hours: int = 24) -> List[Dict[str, Any]]:
        """Simulate historical DEX scans by running scans at intervals."""
        logger.info(f"Running simulated historical scans: {days} days, every {interval_hours}h")
        
        scan_history = []
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)
        current = start_time
        
        while current < end_time:
            scan_time = current.strftime("%Y-%m-%dT%H:%M:%SZ")
            logger.info(f"  Scanning at {scan_time}...")
            
            try:
                result = self.scanner.full_scan(chain=self.chain)
                result["scan_time"] = scan_time
                scan_history.append({
                    "scan_time": scan_time,
                    "signals": result.get("top_trending", []) + result.get("top_new_pools", []),
                    "summary": result.get("summary"),
                })
            except Exception as e:
                logger.warning(f"Scan failed at {scan_time}: {e}")
                scan_history.append({
                    "scan_time": scan_time,
                    "signals": [],
                    "summary": f"FAILED: {e}",
                })
            
            current += timedelta(hours=interval_hours)
            time.sleep(2)  # Rate limit friendly
        
        return scan_history

    def save_scan_history(self, scan_history: List[Dict[str, Any]]) -> None:
        """Save scan history to JSON file."""
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, "w") as f:
            json.dump(scan_history, f, indent=2)
        logger.info(f"Saved scan history to {HISTORY_FILE} ({len(scan_history)} scans)")

    def load_scan_history(self) -> List[Dict[str, Any]]:
        """Load scan history from JSON file."""
        if not HISTORY_FILE.exists():
            return []
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)

    def fetch_kucoin_listings(self, listings_file: Path) -> Dict[str, Any]:
        """Fetch known KuCoin listings (symbol -> listing date)."""
        if listings_file.exists():
            with open(listings_file, "r") as f:
                return json.load(f)
        return {}

    def check_cex_listing(self, base_token: str, kucoin_listings: Dict[str, Any]) -> Optional[Dict]:
        """Check if a token is listed on KuCoin and get listing date."""
        # Normalize token symbol
        base = base_token.upper()
        for listing in kucoin_listings.get("listings", []):
            if listing.get("symbol", "").upper() == base:
                return listing
        return None

    def fetch_price_performance(self, pair: str, signal_time: str, lookforward_days: int = 7) -> Optional[Dict]:
        """Fetch price performance after signal time using KuCoin klines."""
        try:
            signal_dt = datetime.fromisoformat(signal_time.replace("Z", "+00:00"))
            end_dt = signal_dt + timedelta(days=lookforward_days)
            
            df = self.klines_fetcher.fetch_klines(
                self.exchange_adapter, pair, interval="1hour", candle_count=200
            )
            
            if df is None or df.empty:
                return None
            
            # Find closest candle to signal time
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            signal_candles = df[df["timestamp"] >= signal_dt]
            
            if signal_candles.empty:
                return None
            
            entry_price = signal_candles.iloc[0]["close"]
            
            # Get price at lookforward_days
            target_dt = signal_dt + timedelta(days=lookforward_days)
            future_candles = df[df["timestamp"] <= target_dt]
            
            if future_candles.empty:
                return None
            
            exit_price = future_candles.iloc[-1]["close"]
            pct_change = ((exit_price - entry_price) / entry_price) * 100
            
            return {
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "pct_change": round(pct_change, 2),
                "lookforward_days": lookforward_days,
                "candles_analyzed": len(future_candles),
            }
        except Exception as e:
            logger.warning(f"Price performance fetch failed for {pair}: {e}")
            return None

    def run_backtest(self, scan_history: List[Dict[str, Any]], kucoin_listings: Dict[str, Any],
                     min_composite: float = 0.4, lookforward_days: int = 7) -> Dict[str, Any]:
        """Run backtest analysis on scan history."""
        logger.info(f"Running backtest: min_composite={min_composite}, lookforward={lookforward_days}d")
        
        results = {
            "total_scans": len(scan_history),
            "total_signals": 0,
            "strong_buy_signals": 0,
            "buy_signals": 0,
            "listings_found": 0,
            "signals_with_performance": [],
            "summary": {},
        }
        
        for scan in scan_history:
            signals = scan.get("signals", [])
            for sig in signals:
                composite = sig.get("composite_score", 0)
                signal_type = sig.get("signal", "NEUTRAL")
                
                if composite < min_composite:
                    continue
                
                results["total_signals"] += 1
                if signal_type == "STRONG_BUY":
                    results["strong_buy_signals"] += 1
                elif signal_type == "BUY":
                    results["buy_signals"] += 1
                
                base_token = sig.get("pair", "").split("/")[0].split("-")[0]
                pair = f"{base_token}/USDT"  # KuCoin uses /USDT
                
                # Check if listed on KuCoin
                listing = self.check_cex_listing(base_token, kucoin_listings)
                
                signal_result = {
                    "scan_time": scan.get("scan_time"),
                    "pair": sig.get("pair"),
                    "base_token": base_token,
                    "composite_score": composite,
                    "signal": signal_type,
                    "confidence_tier": sig.get("confidence_tier"),
                    "listed_on_kucoin": listing is not None,
                    "listing_date": listing.get("date") if listing else None,
                    "price_performance": None,
                }
                
                if listing:
                    results["listings_found"] += 1
                    # Fetch price performance after signal
                    perf = self.fetch_price_performance(pair, scan["scan_time"], lookforward_days)
                    if perf:
                        signal_result["price_performance"] = perf
                        results["signals_with_performance"].append(signal_result)
                else:
                    # Token not yet listed - track for future listing check
                    signal_result["price_performance"] = None
                    results["signals_with_performance"].append(signal_result)
        
        # Compute summary stats
        perf_signals = [s for s in results["signals_with_performance"] if s["price_performance"]]
        if perf_signals:
            changes = [s["price_performance"]["pct_change"] for s in perf_signals]
            results["summary"] = {
                "avg_return_pct": round(sum(changes) / len(changes), 2),
                "median_return_pct": round(sorted(changes)[len(changes)//2], 2),
                "win_rate": round(sum(1 for c in changes if c > 0) / len(changes), 3),
                "max_gain_pct": round(max(changes), 2),
                "max_loss_pct": round(min(changes), 2),
                "signals_with_data": len(perf_signals),
            }
        
        return results


def main():
    parser = argparse.ArgumentParser(description="DEX Signal Backtester")
    parser.add_argument("--days", type=int, default=30, help="Days of historical scans to simulate")
    parser.add_argument("--interval", type=int, default=24, help="Scan interval in hours")
    parser.add_argument("--chain", default="solana", help="Chain to scan (solana, base, ethereum)")
    parser.add_argument("--min-composite", type=float, default=0.4, help="Minimum composite score")
    parser.add_argument("--lookforward", type=int, default=7, help="Lookforward days for performance")
    parser.add_argument("--simulate", action="store_true", help="Run simulated historical scans")
    parser.add_argument("--history-file", default=str(HISTORY_FILE), help="Scan history JSON file")
    parser.add_argument("--listings-file", default=str(KUCOIN_LISTINGS_FILE), help="KuCoin listings JSON file")
    args = parser.parse_args()
    
    history_file = Path(args.history_file)
    listings_file = Path(args.listings_file)
    
    backtester = DexSignalBacktester(chain=args.chain)
    
    if args.simulate:
        # Run simulated historical scans
        scan_history = backtester.run_historical_scans(args.days, args.interval)
        backtester.save_scan_history(scan_history)
    else:
        # Load existing scan history
        if not history_file.exists():
            logger.error(f"No scan history found at {history_file}. Run with --simulate first.")
            return 1
        with open(history_file, "r") as f:
            scan_history = json.load(f)
    
    # Load KuCoin listings
    kucoin_listings = backtester.fetch_kucoin_listings(listings_file)
    if not kucoin_listings:
        logger.warning(f"No KuCoin listings data found at {listings_file}.")
        logger.warning("Format: {\"listings\": [{\"symbol\": \"BONK\", \"date\": \"2023-12-15\"}, ...]}")
    
    # Run backtest
    results = backtester.run_backtest(
        scan_history, kucoin_listings,
        min_composite=args.min_composite,
        lookforward_days=args.lookforward
    )
    
    # Print results
    print("\n" + "="*60)
    print("DEX SIGNAL BACKTEST RESULTS")
    print("="*60)
    print(f"Total scans:           {results['total_scans']}")
    print(f"Total signals (>= {args.min_composite}): {results['total_signals']}")
    print(f"  STRONG_BUY:          {results['strong_buy_signals']}")
    print(f"  BUY:                 {results['buy_signals']}")
    print(f"Tokens listed on KuCoin: {results['listings_found']}")
    
    if results["summary"]:
        s = results["summary"]
        print(f"\nPrice Performance (lookforward={args.lookforward}d):")
        print(f"  Signals with data:   {s['signals_with_data']}")
        print(f"  Avg return:          {s['avg_return_pct']}%")
        print(f"  Median return:       {s['median_return_pct']}%")
        print(f"  Win rate:            {s['win_rate']:.1%}")
        print(f"  Max gain:            {s['max_gain_pct']}%")
        print(f"  Max loss:            {s['max_loss_pct']}%")
    
    # Save detailed results
    output_file = Path(f"reports/dex_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results saved to: {output_file}")
    
    return 0


if __name__ == "__main__":
    import pandas as pd
    sys.exit(main())