"""
Unified continuous trading pipeline for KuCoin Lane.

Combines:
1. DEX Intelligence scanning (trending, new pools, phantom launches)
2. Polymarket prediction market odds (airdrop probs, regulatory, listings)
3. Pre-launch token scanning (pump.fun, Birdeye, DexScreener new pairs)
4. Creator intelligence (Helius resolution + reputation)
5. Trading decisions (scoring + thresholds)
6. Jupiter DEX execution (paper trading with REAL quotes)
7. Paper trade monitoring (SL/TP auto-close + P&L tracking)
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.trading.paper_trade_ledger import PaperTradeLedger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("unified_pipeline")


def load_config(config_path: str = "config.json") -> Dict[str, Any]:
    """Load configuration from JSON file."""
    path = Path(config_path)
    if not path.exists():
        logger.warning(f"Config file {config_path} not found, using defaults")
        return {}
    with open(path) as f:
        return json.load(f)


def scan_dex_intelligence(config: Dict[str, Any]) -> Dict[str, Any]:
    """Scan DEX sources for trending tokens and new pools."""
    from src.data.dex_intelligence.scanner import DexScanner
    from src.data.dex_intelligence.dexscreener import DexScreenerProvider
    
    logger.info("[1/5] Scanning DEX intelligence...")
    scanner = DexScanner(chains=["solana"])
    scan_result = scanner.full_scan(chain="solana")
    
    trending = scan_result.get("top_trending", [])
    new_pools = scan_result.get("top_new_pools", [])
    phantom = scan_result.get("phantom_recent_launches", [])
    
    # Also get new pairs from DexScreener token-profiles (has mint + ticker)
    ds = DexScreenerProvider()
    new_pairs = ds.new_pairs(chain_id="solana", limit=50)
    logger.info(f"  New pairs (token-profiles): {len(new_pairs)} tokens")
    
    logger.info(f"  Trending: {scan_result.get('trending_count', 0)} tokens")
    logger.info(f"  New pools: {scan_result.get('new_pools_count', 0)} pools")
    logger.info(f"  Phantom launches: {scan_result.get('phantom_count', 0)}")
    
    return {
        "trending": trending,
        "new_pools": new_pools,
        "phantom": phantom,
        "new_pairs": new_pairs,  # Has mint + ticker
        "scan_time": scan_result.get("scan_time", ""),
        "summary": scan_result.get("summary", ""),
    }


def scan_polymarket(config: Dict[str, Any]) -> Dict[str, Any]:
    """Scan Polymarket for crypto-relevant prediction market odds."""
    from src.data.dex_intelligence.polymarket import get_polymarket_provider
    
    logger.info("[2/6] Scanning Polymarket prediction markets...")
    provider = get_polymarket_provider()
    
    # Get crypto events and markets
    crypto_events = provider.get_crypto_events(limit=20)
    crypto_markets = provider.get_crypto_markets(limit=30)
    airdrop_odds = provider.get_airdrop_odds()
    regulatory_odds = provider.get_regulatory_odds()
    
    logger.info(f"  Crypto events: {len(crypto_events)}")
    logger.info(f"  Crypto markets: {len(crypto_markets)}")
    logger.info(f"  Airdrop odds: {len(airdrop_odds)}")
    logger.info(f"  Regulatory odds: {len(regulatory_odds)}")
    
    # Log notable odds
    for name, market in airdrop_odds.items():
        logger.info(f"  Airdrop: {name} -> Yes={market.get('yes_price', 0):.4f} (Vol: ${market.get('volume', 0):,.0f})")
    
    for question, market in list(regulatory_odds.items())[:5]:
        logger.info(f"  Regulatory: {question[:60]} -> Yes={market.get('yes_price', 0):.4f}")
    
    return {
        "crypto_events": crypto_events,
        "crypto_markets": [provider.normalize_market(m) for m in crypto_markets],
        "airdrop_odds": airdrop_odds,
        "regulatory_odds": regulatory_odds,
    }


def scan_prelaunch(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Scan pre-launch sources for new tokens."""
    from src.intelligence.chain.prelaunch_scanner import PreLaunchScanner
    
    logger.info("[3/6] Scanning pre-launch sources...")
    scanner = PreLaunchScanner()
    limit = config.get("intelligence", {}).get("prelaunch_limit", 50)
    tokens = scanner.scan_all_sources(limit=limit, resolve_creators=True)
    
    logger.info(f"  Pre-launch tokens: {len(tokens)}")
    return tokens


def resolve_creators(dex_data: Dict[str, Any], prelaunch_tokens: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve creator wallets and update registry."""
    from src.intelligence.creator_tracker import CreatorTrackerAgent
    
    logger.info("[3/5] Resolving creators via Helius...")
    
    # Build dex_signals from DEX scan
    dex_signals = []
    for token in dex_data.get("trending", []):
        base_token = token.get("base_token", {})
        dex_signals.append({
            "pair": token.get("pair", base_token.get("symbol", "") + "/SOL"),
            "mint": base_token.get("address", token.get("mint", token.get("address", ""))),
            "symbol": base_token.get("symbol", "UNKNOWN"),
            "deployer": token.get("deployer", "unknown"),
            "composite_score": token.get("composite_score", 0.0),
            "signal": token.get("signal", "NEUTRAL"),
            "scan_time": dex_data.get("scan_time", ""),
            "twitter": token.get("twitter", ""),
            "telegram": token.get("telegram", ""),
            "website": token.get("website", ""),
            "dex_id": token.get("dex_id", ""),
        })
    
    # Build pumpfun_tokens from phantom launches
    pumpfun_tokens = []
    for token in dex_data.get("phantom", []):
        pumpfun_tokens.append({
            "mint": token.get("mint", token.get("address", "")),
            "ticker": token.get("symbol", token.get("ticker", "")),
            "name": token.get("name", ""),
            "created_at": token.get("created_at", dex_data.get("scan_time", "")),
            "creator": token.get("creator", token.get("deployer", "unknown")),
            "factory": "phantom",
            "social_links": {
                "twitter": [token.get("twitter", "")] if token.get("twitter") else [],
                "telegram": [token.get("telegram", "")] if token.get("telegram") else [],
            },
            "community_score": token.get("composite_score", 0.0),
        })
    
    # Add new pairs from DexScreener token-profiles (has mint + ticker)
    for token in dex_data.get("new_pairs", []):
        mint = token.get("mint", "")
        if not mint or len(mint) < 32:
            continue
        pumpfun_tokens.append({
            "mint": mint,
            "ticker": token.get("ticker", "UNKNOWN"),
            "name": token.get("name", ""),
            "created_at": token.get("updated_at", dex_data.get("scan_time", "")),
            "creator": "unknown",  # Will be resolved by tracker
            "factory": "dexscreener_new",
            "social_links": {
                "twitter": [token.get("social_links", {}).get("twitter", "")] if token.get("social_links", {}).get("twitter") else [],
                "telegram": [token.get("social_links", {}).get("telegram", "")] if token.get("social_links", {}).get("telegram") else [],
            },
            "community_score": 0.5,  # Default for new pairs
        })
    
    # Add pre-launch tokens (creator resolution will happen in tracker)
    for token in prelaunch_tokens:
        mint = token.get("mint", "")
        # Skip invalid mints (Ethereum addresses)
        if mint.startswith("0x") or len(mint) < 32:
            continue
        pumpfun_tokens.append({
            "mint": mint,
            "ticker": token.get("symbol", "UNKNOWN"),
            "name": token.get("name", "Unknown"),
            "created_at": token.get("discovered_at", ""),
            "creator": token.get("creator_wallet", "unknown"),
            "factory": "prelaunch",
            "social_links": token.get("social_links", {"twitter": [], "telegram": []}),
            "community_score": token.get("community_score", 0.0),
        })
    
    logger.info(f"  Signals to process: {len(dex_signals)} DEX + {len(pumpfun_tokens)} pumpfun/prelaunch/new_pairs")
    
    tracker = CreatorTrackerAgent(config={
        "creator_db_path": "data/creator_registry.json"
    })
    
    tracker_result = tracker.execute({
        "dex_signals": dex_signals,
        "pumpfun_tokens": pumpfun_tokens,
    })
    
    # Persist enriched dex signals
    Path("data").mkdir(exist_ok=True)
    with open("data/latest_dex_signals.json", "w") as f:
        json.dump(dex_signals, f, indent=2)
    
    tracker_data = tracker_result.get("data", {})
    new_creators = tracker_data.get("new_creators", [])
    alpha_creators = tracker.get_alpha_creators(min_score=0.3)
    
    logger.info(f"  Creator Registry: {tracker_data.get('creator_count', 0)} total, {len(new_creators)} new, {tracker_data.get('alpha_count', 0)} alpha")
    
    return {
        "dex_signals": dex_signals,
        "pumpfun_tokens": pumpfun_tokens,
        "creator_count": tracker_data.get("creator_count", 0),
        "new_creators": new_creators,
        "alpha_creators": alpha_creators,
    }


def make_trade_decisions(
    dex_signals: List[Dict[str, Any]],
    pumpfun_tokens: List[Dict[str, Any]],
    creator_data: Dict[str, Any],
    config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Generate buy decisions from enriched signals."""
    from src.intelligence.trading_decision import make_trade_decisions as make_decisions
    
    logger.info("[4/5] Making trade decisions...")
    
    threshold = config.get("trading", {}).get("min_signal_score", 0.35)
    min_boost = config.get("trading", {}).get("min_creator_boost", 1.0)
    
    # Convert pumpfun_tokens to format expected by make_trade_decisions
    enriched_tokens = []
    for token in pumpfun_tokens:
        enriched_tokens.append({
            "mint": token.get("mint", ""),
            "symbol": token.get("ticker", "UNKNOWN"),
            "name": token.get("name", ""),
            "community_score": token.get("community_score", 0.0),
            "pre_launch_tier": "HIGH_CONFIDENCE" if token.get("community_score", 0) > 0.7 else "SPECULATIVE",
            "creator_wallet": token.get("creator", "unknown"),
            "creator_boost": 1.0,  # Will be enhanced by creator data
        })
    
    # Also add DEX signals that have mint addresses
    for signal in dex_signals:
        if signal.get("mint"):
            enriched_tokens.append({
                "mint": signal["mint"],
                "symbol": signal.get("symbol", "UNKNOWN"),
                "community_score": signal.get("composite_score", 0.0),
                "pre_launch_tier": "SPECULATIVE",
                "creator_wallet": signal.get("deployer", "unknown"),
        "creator_boost": 1.0,
    })

    from src.intelligence.creator_intel import get_creator_boost
    for token in enriched_tokens:
        wallet = token.get("creator") or token.get("creator_wallet") or token.get("deployer", "unknown")
        token["creator_boost"] = get_creator_boost(wallet)

    # Convert dicts to TokenInfo objects
    from src.intelligence.chain.token_models import tokens_to_tokeninfo_list
    token_infos = tokens_to_tokeninfo_list(enriched_tokens)
    
    decisions = make_decisions(token_infos, min_community_score=threshold, min_boost=min_boost)
    
    # Convert TradeDecision objects back to dicts for compatibility
    filtered = []
    for d in decisions:
        creator_boost = d.boost
        if creator_boost >= min_boost:
            filtered.append({
                "mint": d.token.mint,
                "symbol": d.token.ticker,
                "action": d.action,
                "confidence": d.confidence,
                "boost": d.boost,
                "reason": d.reason,
                "suggested_size_pct": d.suggested_size_pct,
                "creator_boost": d.boost,
            })
    
    logger.info(f"  Decisions: {len(decisions)} raw -> {len(filtered)} after creator boost filter (min={min_boost})")
    
    return filtered


def execute_trades(
    decisions: List[Dict[str, Any]],
    ledger: PaperTradeLedger,
    config: Dict[str, Any],
    jupiter_executor
) -> List[Dict[str, Any]]:
    """Execute paper trades with REAL Jupiter quotes."""
    from src.execution.dex_jupiter_executor import JupiterDexExecutor
    
    logger.info("[5/5] Executing paper trades...")
    
    if not decisions:
        logger.info("  No signals to execute")
        return []
    
    if jupiter_executor is None:
        sol_per_trade = config.get("trading", {}).get("sol_per_trade", 0.05)
        jupiter_executor = JupiterDexExecutor(paper_trading=True, sol_amount=sol_per_trade)
    
    # Get current prices for monitoring existing positions
    current_prices = {}
    for trade in ledger.get_open_trades():
        pair = trade["pair"]
        # We'll fetch prices during monitoring step
    
    # Monitor existing open positions FIRST (close SL/TP hits)
    closed = monitor_positions(ledger, current_prices)
    if closed:
        logger.info(f"  Auto-closed {len(closed)} positions on SL/TP")
    
    # Execute new trades
    executed = []
    max_positions = config.get("trading", {}).get("max_tokens_per_cycle", 10)
    
    for i, decision in enumerate(decisions[:max_positions]):
        mint = decision.get("mint", "")
        symbol = decision.get("symbol", "?")
        score = decision.get("score", 0)
        
        if not mint:
            continue
        
        # Skip invalid mints (Ethereum addresses, too short, etc.)
        from src.execution.dex_jupiter_executor import is_valid_solana_mint
        if not is_valid_solana_mint(mint):
            logger.debug(f"  Skipping invalid mint: {mint}")
            continue
        
        logger.info(f"  Processing {symbol} ({mint[:8]}...) score={score}")
        
        # Execute paper trade via Jupiter (gets real quote for price)
        result = jupiter_executor.execute_swap(mint, direction="buy")
        
        if result.get("success"):
            price = result.get("price", 0)
            estimated_output = result.get("estimated_output", 0)
            
            # Open paper trade with REAL Jupiter price
            stop_loss_pct = config.get("risk", {}).get("stop_loss_pct", 0.15)
            take_profit_pct = config.get("risk", {}).get("take_profit_pct", 0.5)
            
            if price > 0:
                entry_price = price
                stop_loss = entry_price * (1 - stop_loss_pct)
                take_profit = entry_price * (1 + take_profit_pct)
                
                trade_id = ledger.open_trade(
                    pair=f"{symbol}/SOL",
                    direction="long",
                    entry_price=entry_price,
                    position_size=estimated_output,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    signal_strength=score,
                    intelligence_confidence=score,
                    intelligence_action="BUY",
                    metadata={
                        "source": "unified_pipeline",
                        "mint": mint,
                        "creator_boost": decision.get("creator_boost", 1.0),
                        "jupiter_quote": result.get("quote"),
                    }
                )
                
                executed.append({
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "mint": mint,
                    "entry_price": entry_price,
                    "position_size": estimated_output,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "score": score,
                })
                
                logger.info(f"    OPENED trade #{trade_id}: {symbol} @ {entry_price:.6f} SOL (size={estimated_output:.2f}) SL={stop_loss:.6f} TP={take_profit:.6f}")
            else:
                logger.warning(f"    No valid price for {symbol}, skipping")
        else:
            logger.warning(f"    Failed to execute {symbol}: {result.get('error', 'unknown')}")
    
    return executed


def monitor_positions(ledger: PaperTradeLedger, current_prices: Dict[str, float]) -> List[Dict[str, Any]]:
    """Check open positions against current prices, auto-close on SL/TP."""
    # Fetch current prices from Jupiter for all open positions
    from src.execution.dex_jupiter_executor import JupiterDexExecutor
    
    jupiter = JupiterDexExecutor(paper_trading=True)
    open_trades = ledger.get_open_trades()
    
    if not open_trades:
        return []
    
    # Build price map from Jupiter quotes
    prices = {}
    for trade in open_trades:
        pair = trade["pair"]  # e.g., "WIF/SOL"
        symbol = pair.split("/")[0]
        
        # We need the mint address to query Jupiter
        mint = trade.get("metadata", {}).get("mint")
        if mint:
            # For monitoring, we need price in SOL terms
            # Query token -> SOL
            quote = jupiter.get_quote(mint, "So11111111111111111111111111111111111111112", amount=trade["position_size"])
            if quote:
                price = jupiter.get_price_from_quote(quote, mint, "So11111111111111111111111111111111111111112")
                if price:
                    prices[pair] = price
    
    # Use ledger's monitor function
    closed = ledger.monitor_open_positions(prices)
    return closed


def save_cycle_summary(
    cycle_num: int,
    dex_data: Dict[str, Any],
    polymarket_data: Dict[str, Any],
    prelaunch_count: int,
    creator_data: Dict[str, Any],
    decisions: List[Dict[str, Any]],
    executed: List[Dict[str, Any]],
    config: Dict[str, Any]
) -> None:
    """Save cycle summary to signal log."""
    Path("data").mkdir(exist_ok=True)
    
    summary = {
        "cycle": cycle_num,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dex_trending": len(dex_data.get("trending", [])),
        "dex_new_pools": len(dex_data.get("new_pools", [])),
        "dex_phantom": len(dex_data.get("phantom", [])),
        "polymarket_events": len(polymarket_data.get("crypto_events", [])),
        "polymarket_markets": len(polymarket_data.get("crypto_markets", [])),
        "polymarket_airdrops": len(polymarket_data.get("airdrop_odds", [])),
        "polymarket_regulatory": len(polymarket_data.get("regulatory_odds", [])),
        "prelaunch_tokens": prelaunch_count,
        "creator_registry_size": creator_data.get("creator_count", 0),
        "new_creators": len(creator_data.get("new_creators", [])),
        "alpha_creators": len(creator_data.get("alpha_creators", [])),
        "decisions_generated": len(decisions),
        "trades_executed": len(executed),
        "config_threshold": config.get("trading", {}).get("min_signal_score", 0.35),
        "config_min_boost": config.get("trading", {}).get("min_creator_boost", 1.0),
    }
    
    signal_log_path = Path("data/signal_log.json")
    if signal_log_path.exists():
        existing = json.load(open(signal_log_path))
    else:
        existing = []
    
    existing.append(summary)
    existing = existing[-500:]
    json.dump(existing, open(signal_log_path, "w"), indent=2)
    
    # Also save latest cycle
    with open("data/latest_cycle.json", "w") as f:
        json.dump(summary, f, indent=2)


def run_cycle(cycle_num: int, config: Dict[str, Any], ledger: PaperTradeLedger, jupiter_executor) -> Dict[str, Any]:
    """Run one complete pipeline cycle."""
    logger.info(f"{'='*60}")
    logger.info(f"UNIFIED PIPELINE CYCLE #{cycle_num} - {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"{'='*60}")
    
    # Step 1: DEX Intelligence
    dex_data = scan_dex_intelligence(config)
    
    # Step 2: Polymarket prediction markets
    polymarket_data = scan_polymarket(config)
    
    # Step 3: Pre-launch scanning
    prelaunch_tokens = scan_prelaunch(config)
    
    # Step 4: Creator resolution
    creator_data = resolve_creators(dex_data, prelaunch_tokens)
    
    # Step 5: Trade decisions
    decisions = make_trade_decisions(
        dex_data.get("dex_signals", []),
        creator_data.get("pumpfun_tokens", []),
        creator_data,
        config
    )
    
    # Step 6: Execute & monitor
    executed = execute_trades(decisions, ledger, config, jupiter_executor)
    
    # Save summary
    save_cycle_summary(
        cycle_num, dex_data, polymarket_data, len(prelaunch_tokens), 
        creator_data, decisions, executed, config
    )
    
    # Log ledger stats
    stats = ledger.get_statistics()
    logger.info(f"  Ledger: {stats['total_trades']} closed, {stats['open_trades']} open, "
                f"Win rate: {stats['win_rate']:.1%}, P&L: ${stats['total_pnl_usd']:.2f}")
    
    return {
        "cycle": cycle_num,
        "dex_data": dex_data,
        "polymarket_data": polymarket_data,
        "prelaunch_count": len(prelaunch_tokens),
        "creator_data": creator_data,
        "decisions": decisions,
        "executed": executed,
        "ledger_stats": stats,
    }


def main():
    parser = argparse.ArgumentParser(description="KuCoin Lane Unified Trading Pipeline")
    parser.add_argument("--interval-min", type=int, default=15, help="Cycle interval in minutes")
    parser.add_argument("--config", type=str, default="config.json", help="Config file path")
    parser.add_argument("--ledger", type=str, default="paper_trades_ledger.json", help="Paper trade ledger file")
    parser.add_argument("--sol-per-trade", type=float, default=0.05, help="SOL amount per trade")
    parser.add_argument("--threshold", type=float, default=None, help="Min signal score (overrides config)")
    parser.add_argument("--min-boost", type=float, default=None, help="Min creator boost (overrides config)")
    parser.add_argument("--max-cycles", type=int, default=0, help="Max cycles (0 = infinite)")
    parser.add_argument("--single-cycle", action="store_true", help="Run once and exit")
    args = parser.parse_args()
    
    config = load_config(args.config)
    
    # Override config with CLI args
    if args.sol_per_trade:
        config.setdefault("trading", {})["sol_per_trade"] = args.sol_per_trade
    if args.threshold is not None:
        config.setdefault("trading", {})["min_signal_score"] = args.threshold
    if args.min_boost is not None:
        config.setdefault("trading", {})["min_creator_boost"] = args.min_boost
    
    logger.info("🚀 KuCoin Lane - UNIFIED Trading Pipeline")
    logger.info(f"   Interval: {args.interval_min} min")
    logger.info(f"   SOL per trade: {args.sol_per_trade}")
    logger.info(f"   Ledger: {args.ledger}")
    logger.info(f"   Config: {args.config}")
    logger.info("")
    
    # Initialize ledger
    ledger = PaperTradeLedger(filepath=args.ledger, initial_balance=147.0)  # $147 real budget
    
    # Initialize Jupiter executor
    from src.execution.dex_jupiter_executor import JupiterDexExecutor
    jupiter_executor = JupiterDexExecutor(paper_trading=True, sol_amount=args.sol_per_trade)
    
    cycle = 0
    interval_seconds = args.interval_min * 60
    
    try:
        while True:
            cycle += 1
            logger.info(f">>> CYCLE #{cycle} <<<")
            
            try:
                result = run_cycle(cycle, config, ledger, jupiter_executor)
                logger.info(f"✅ Cycle #{cycle} complete")
                logger.info(f"   Trades executed: {len(result['executed'])}")
                logger.info(f"   Open positions: {result['ledger_stats']['open_trades']}")
                logger.info(f"   Total closed: {result['ledger_stats']['total_trades']}")
            except KeyboardInterrupt:
                logger.info("Stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Cycle #{cycle} failed: {e}", exc_info=True)
            
            if args.single_cycle or (args.max_cycles and cycle >= args.max_cycles):
                logger.info("Single cycle mode / max cycles reached, exiting")
                break
            
            logger.info(f"⏳ Next cycle in {args.interval_min} min...")
            logger.info("")
            time.sleep(interval_seconds)
            
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
    
    # Final report
    logger.info("=" * 60)
    logger.info("FINAL PAPER TRADE REPORT")
    logger.info("=" * 60)
    print(ledger.generate_report())
    
    return 0


if __name__ == "__main__":
    sys.exit(main())