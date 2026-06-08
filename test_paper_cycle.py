#!/usr/bin/env python3
"""Local paper cycle test - full pipeline without exchange auth."""
import os, sys, json, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ['PAPER_TRADING'] = 'true'
os.environ['LIVE_TRADING'] = 'false'

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / 'config' / '.env')

print("=== LOCAL PAPER CYCLE TEST ===")
print(f"PAPER_TRADING: {os.getenv('PAPER_TRADING')}")
print(f"SOLANA_RPC_URL: {(os.getenv('SOLANA_RPC_URL') or '')[:40]}...")
print()

# DEX Intelligence
print("=== DEX INTELLIGENCE SCAN ===")
try:
    from src.data.dex_intelligence_agent import DexIntelligenceAgent
    dex_agent = DexIntelligenceAgent()
    dex_result = dex_agent.execute({"chain": "solana", "min_composite_score": 0.3})
    dex_signals = dex_result.get("data", {}).get("dex_signals", [])
    print(f"DEX signals found: {len(dex_signals)}")
    for s in dex_signals[:3]:
        print(f"  {s.get('pair')}: score={s.get('composite_score'):.2f}, signal={s.get('signal')}")
except Exception as e:
    print(f"DEX error: {e}")
    import traceback; traceback.print_exc()
    dex_signals = []

print()

# Creator Tracker
print("=== CREATOR TRACKER ===")
try:
    from src.intelligence.creator_tracker import CreatorTrackerAgent
    tracker = CreatorTrackerAgent()
    creator_result = tracker.execute({"dex_signals": dex_signals})
    new_creators = creator_result.get("data", {}).get("new_creators", [])
    print(f"New creators detected: {len(new_creators)}")
    for nc in new_creators[:3]:
        print(f"  {nc.get('creator', 'unknown')[:8]}... for {nc.get('token')}")
except Exception as e:
    print(f"Creator error: {e}")

print()

# WhaleWatch (no exchange auth needed for CVD analysis on public klines)
print("=== WHALEWATCH CVD ANALYSIS ===")
try:
    # Check if WhaleWatch can run without exchange keys
    from src.intelligence.whale_watch import WhaleWatch
    # WhaleWatch needs exchange adapter - skip for now
    print("WhaleWatch requires exchange adapter - skipping (no keys)")
except Exception as e:
    print(f"WhaleWatch: {e}")

# Output
output = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "paper_mode": True,
    "dex_signals": len(dex_signals),
    "new_creators": len(new_creators) if 'new_creators' in dir() else 0,
    "ready_for_live": len(dex_signals) > 0,
}

with open("paper_trades_ledger_test.json", "w") as f:
    json.dump(output, f, indent=2)

print("=== TEST COMPLETE ===")
print(f"Status: {'READY FOR LIVE PAPER CYCLE' if output['ready_for_live'] else 'NEEDS WORK'}")