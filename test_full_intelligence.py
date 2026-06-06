#!/usr/bin/env python3
"""Show the full DEX→Creator→Lag→Whale signal chain working."""
import os, sys, json, time, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ['PAPER_TRADING'] = 'true'
os.environ['LIVE_TRADING'] = 'false'

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / 'config' / '.env')

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

print("=" * 60)
print("FULL INTELLIGENCE PIPELINE TEST (DEX → Creator → Lag)")
print("=" * 60)

# 1. DEX Intelligence
print("\n[1] DEX INTELLIGENCE SCAN")
from src.data.dex_intelligence_agent import DexIntelligenceAgent
dex_agent = DexIntelligenceAgent(config={"enable_creator_tracking": True})
dex_result = dex_agent.execute({"chain": "solana", "min_composite_score": 0.3})
dex_signals = dex_result.get("data", {}).get("dex_signals", [])
print(f"   Found {len(dex_signals)} DEX signals with composite_score >= 0.3")

# 2. Creator Tracking  
print("\n[2] CREATOR TRACKING")
from src.intelligence.creator_tracker import CreatorTrackerAgent
tracker = CreatorTrackerAgent()
creator_result = tracker.execute({"dex_signals": dex_signals})
new_creators = creator_result.get("data", {}).get("new_creators", [])
print(f"   {len(new_creators)} new creators detected, {creator_result.get('data', {}).get('creator_count', 0)} total tracked")

# 3. DEX→CEX Lag Detection
print("\n[3] DEX→CEX LAG DETECTION")
from src.intelligence.lead_lag import DexToCexLagDetector
lag_detector = DexToCexLagDetector(lag_window_days=30, min_composite_score=0.4)
lag_signals = lag_detector.run(dex_signals=dex_signals)
opps = [s for s in lag_signals if s.get("lead_lag_signal") == "OPPORTUNITY"]
watches = [s for s in lag_signals if s.get("lead_lag_signal") == "WATCH"]
stales = [s for s in lag_signals if s.get("lead_lag_signal") == "STALE"]
print(f"   OPPORTUNITIES: {len(opps)}, WATCH: {len(watches)}, STALE: {len(stales)}")
if opps:
    print(f"   Top OPPORTUNITY: {opps[0].get('pair')} (score={opps[0].get('composite_score'):.2f})")

# 4. WhaleWatch CVD analysis (using simulated data since no exchange)
print("\n[4] WHALEWATCH CVD ANALYSIS")
print("   (Skipped - requires exchange klines; CVD works on OHLCV data)")

# 5. Signal Summary for KuCoin paper trade
print("\n" + "=" * 60)
print("TRADE CANDIDATES FOR PAPER TRADING")
print("=" * 60)

# Combine signals
trade_candidates = []
for signal in dex_signals:
    pair = signal.get("pair", "").split("/")[0]  # Get token symbol from pair
    base_score = signal.get("composite_score", 0.0)
    boosted_score = base_score
    
    # Check if this pair is in a lag opportunity
    for opp in opps:
        if opp.get("pair", "").split("/")[0] in signal.get("pair", ""):
            boosted_score *= 1.3  # DEX_CEX_OPPORTUNITY_MULTIPLIER
            signal["lag_opportunity"] = True
    
    trade_candidates.append({
        "pair": signal.get("pair"),
        "base_score": base_score,
        "boosted_score": min(1.0, boosted_score),
        "signal": signal.get("signal"),
        "lag_opportunity": signal.get("lag_opportunity", False),
    })

# Sort by boosted score
trade_candidates.sort(key=lambda x: x["boosted_score"], reverse=True)

for tc in trade_candidates[:5]:
    marker = "🚀" if tc["lag_opportunity"] else ""
    print(f"   {tc['pair']}: {tc['base_score']:.2f} → {tc['boosted_score']:.3f} [{tc['signal']}] {marker}")

# Output
output = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "dex_signals": len(dex_signals),
    "new_creators": len(new_creators),
    "lag_opportunities": len(opps),
    "top_candidate": trade_candidates[0]["pair"] if trade_candidates else None,
    "ready_for_live_paper": len(dex_signals) > 0 and len(opps) > 0,
}

with open("paper_trades_ledger_test.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\n✓ Output saved to paper_trades_ledger_test.json")
print(f"✓ READY FOR LIVE PAPER CYCLE: {output['ready_for_live_paper']}")