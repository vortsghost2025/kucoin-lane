#!/usr/bin/env python3
"""
run_creator_pipeline.py - Continuous creator registry population.

Fetches fresh pre-launch tokens, resolves creator wallets via Helius, and
builds CreatorProfile entries with reputation scores in data/creator_registry.json.

Usage:
    python run_creator_pipeline.py
    python run_creator_pipeline.py --continuous --interval-min 30 --limit 20
"""

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.intelligence.chain.prelaunch_scanner import PreLaunchScanner
from src.intelligence.creator_tracker import CreatorTrackerAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("creator_pipeline")


def run_creator_cycle(limit: int = 50, agent: "CreatorTrackerAgent" = None) -> dict:
    """Fetch tokens, resolve creators, and populate registry. Returns stats."""
    if agent is None:
        agent = CreatorTrackerAgent()

    print(f"[CREATOR] Scanning {limit} pre-launch tokens with creator resolution...")
    scanner = PreLaunchScanner()
    tokens = scanner.scan_all_sources(limit=limit, resolve_creators=True)

    resolved = sum(1 for t in tokens if t.get("creator"))
    print(f"[CREATOR] Scanned {len(tokens)} tokens, {resolved} with resolved creators")

    # Convert tokens to signals format for CreatorTrackerAgent
    signals = []
    for t in tokens:
        mint = t.get("mint", "")
        creator = t.get("creator", "")
        if not mint:
            continue
        score = t.get("community_score", 0.0)
        signal_type = "BUY" if score >= 0.3 else "NEUTRAL"
        signals.append({
            "pair": f"{t.get('ticker', mint[:8])}/SOL",
            "mint": mint,
            "deployer": creator if creator else "unknown",
            "composite_score": score,
            "signal": signal_type,
            "scan_time": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        })

    known = sum(1 for s in signals if s["deployer"] in agent.creator_profiles)
    print(f"[CREATOR] {len(signals)} signals, {known} from known creators")

    result = agent.execute({"dex_signals": signals})
    print(f"[CREATOR] Registry updated: {result['data']['creator_count']} total creators, "
          f"{len(result['data']['new_creators'])} new")

    alphas = agent.get_alpha_creators(min_score=0.3)
    print(f"[CREATOR] Alpha creators (score >= 0.3): {len(alphas)}")
    for a in alphas[:5]:
        print(f"  {a.display_name} | score={a.reputation_score:.3f} | tokens={len(a.token_history)} | tags={a.tags}")

    return {
        "tokens_scanned": len(tokens),
        "resolved_creators": resolved,
        "signals": len(signals),
        "total_creators": result["data"]["creator_count"],
        "new_creators": len(result["data"]["new_creators"]),
        "alpha_count": len(alphas),
        "registry_path": str(agent.db_path),
    }


def run_continuous(limit: int = 50, interval_min: int = 30, agent: "CreatorTrackerAgent" = None) -> None:
    """Continuous creator registry population loop."""
    print(f"[CREATOR] Starting continuous mode: {limit} tokens every {interval_min}min")

    if agent is None:
        agent = CreatorTrackerAgent()

    _running = True

    def _signal_handler(signum, frame):
        nonlocal _running
        logger.info(f"Signal {signum}, shutting down...")
        _running = False

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    cycle = 0
    while _running:
        cycle += 1
        print(f"\n=== CREATOR CYCLE {cycle} ===")
        try:
            stats = run_creator_cycle(limit=limit, agent=agent)
            print(f"[CREATOR] Cycle {cycle} done. Registry: {stats['total_creators']} creators, "
                  f"{stats['alpha_count']} alpha. Sleeping {interval_min}min...")
        except Exception as e:
            logger.error(f"Cycle {cycle} error: {e}")

        if _running:
            time.sleep(interval_min * 60)

    print(f"[CREATOR] Shutting down. Final registry: {agent.db_path}")
    print(f"[CREATOR] Total creators: {len(agent.creator_profiles)}")
    print(f"[CREATOR] Alphas: {len(agent.get_alpha_creators(min_score=0.3))}")


def main():
    parser = argparse.ArgumentParser(description="Populate creator registry with real on-chain data")
    parser.add_argument("--limit", type=int, default=50, help="Max tokens to scan per cycle")
    parser.add_argument("--continuous", action="store_true", help="Run in continuous loop")
    parser.add_argument("--interval-min", type=int, default=30, help="Minutes between cycles")
    parser.add_argument("--db-path", type=str, default="data/creator_registry.json",
                        help="Path to creator registry JSON file")
    args = parser.parse_args()

    print(f"=== run_creator_pipeline.py | limit={args.limit} | continuous={args.continuous} ===")

    agent = CreatorTrackerAgent(config={"creator_db_path": args.db_path})

    if args.continuous:
        run_continuous(limit=args.limit, interval_min=args.interval_min, agent=agent)
    else:
        stats = run_creator_cycle(limit=args.limit, agent=agent)
        print(f"\n[CREATOR] Pipeline complete.")
        print(f"  Registry: {stats['registry_path']}")
        print(f"  Total creators: {stats['total_creators']}")
        print(f"  New this run: {stats['new_creators']}")
        print(f"  Alpha creators: {stats['alpha_count']}")
        print(f"  Tokens with resolved creators: {stats['resolved_creators']} / {stats['tokens_scanned']}")

        if stats["total_creators"] > 0:
            print(f"\n[CREATOR] Registry ready. The trading pipeline will now use real creator boosts.")
            print(f"[CREATOR] Next: run_pipeline.py will find BUY signals when boost > 1.05")


if __name__ == "__main__":
    main()
