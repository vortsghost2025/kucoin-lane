#!/usr/bin/env python3
"""DEX Scanner Agent Entry Point"""

import sys
import argparse
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from context import read_context, write_context, update_context, record_scan_result, update_api_latency

def scan_phantom(limit=50, min_market_cap=0, min_liquidity=0):
    """Scan Phantom.com for new launches."""
    # Import the actual scanner
    from data.dex_intelligence.phantom import PhantomLauncherScanner
    
    scanner = PhantomLauncherScanner()
    tokens = scanner.scan_new_launches()
    
    # Filter
    filtered = [
        t for t in tokens
        if t.get("marketCap", 0) >= min_market_cap
        and t.get("liquidity", 0) >= min_liquidity
    ][:limit]
    
    return filtered

def scan_pumpfun(limit=50, min_market_cap=0, min_liquidity=0):
    """Scan PumpFun for new launches."""
    from data.dex_intelligence.pumpfun import scan_pumpfun_launches
    tokens = scan_pumpfun_launches(limit=limit)
    return [t for t in tokens if t.get("marketCap", 0) >= min_market_cap and t.get("liquidity", 0) >= min_liquidity]

def scan_birdeye(limit=50, min_market_cap=0, min_liquidity=0):
    """Scan Birdeye for new pairs."""
    from data.dex_intelligence.birdeye import BirdeyeProvider
    provider = BirdeyeProvider()
    tokens = provider.get_new_pairs(limit=limit)
    return [t for t in tokens if t.get("marketCap", 0) >= min_market_cap and t.get("liquidity", 0) >= min_liquidity]

def scan_dexscreener(limit=50, min_market_cap=0, min_liquidity=0):
    """Scan DexScreener for new pairs."""
    from data.dex_intelligence.dexscreener import DexScreenerProvider
    provider = DexScreenerProvider()
    tokens = provider.new_pairs(chain_id="solana", limit=limit)
    return [t for t in tokens if t.get("marketCap", 0) >= min_market_cap and t.get("liquidity", 0) >= min_liquidity]

def scan_polymarket(limit=50):
    """Scan Polymarket for crypto odds."""
    from data.dex_intelligence.polymarket import get_polymarket_provider
    provider = get_polymarket_provider()
    return provider.get_crypto_events(limit=limit)

def main():
    parser = argparse.ArgumentParser(description="DEX Scanner Agent")
    parser.add_argument("action", choices=["scan", "status"])
    parser.add_argument("--source", choices=["phantom", "pumpfun", "birdeye", "dexscreener", "polymarket", "all"], default="all")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--min-market-cap", type=float, default=0)
    parser.add_argument("--min-liquidity", type=float, default=0)
    args = parser.parse_args()
    
    if args.action == "status":
        ctx = read_context()
        print(json.dumps(ctx.get("scan_results", {}), indent=2, default=str))
        return
    
    results = {}
    errors = {}
    
    sources = [args.source] if args.source != "all" else ["phantom", "pumpfun", "birdeye", "dexscreener", "polymarket"]
    
    for source in sources:
        try:
            if source == "phantom":
                tokens = scan_phantom(args.limit, args.min_market_cap, args.min_liquidity)
            elif source == "pumpfun":
                tokens = scan_pumpfun(args.limit, args.min_market_cap, args.min_liquidity)
            elif source == "birdeye":
                tokens = scan_birdeye(args.limit, args.min_market_cap, args.min_liquidity)
            elif source == "dexscreener":
                tokens = scan_dexscreener(args.limit, args.min_market_cap, args.min_liquidity)
            elif source == "polymarket":
                tokens = scan_polymarket(args.limit)
            else:
                continue
            
            results[source] = tokens
            errors[source] = []
            record_scan_result(source, tokens, [])
            
        except Exception as e:
            errors[source] = [str(e)]
            results[source] = []
            record_scan_result(source, [], [str(e)])
    
    output = {
        "success": len(errors) == 0 or any(results.values()),
        "scan_time": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "sources": sources,
        "tokens_found": sum(len(v) for v in results.values()),
        "results": results,
        "errors": errors
    }
    
    print(json.dumps(output, indent=2, default=str))

if __name__ == "__main__":
    main()