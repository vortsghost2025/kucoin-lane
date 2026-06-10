#!/usr/bin/env python3
"""
Integrate PreLaunchScanner intelligence into creator registry and trading pipeline
This is the primary source of Helius-resolved creator data
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Load env
from dotenv import load_dotenv
load_dotenv('S:/kucoin-lane/.env')

sys.path.insert(0, 'S:/kucoin-lane')

from src.intelligence.chain.prelaunch_scanner import PreLaunchScanner

def integrate_prelaunch_intelligence(limit: int = 100) -> dict:
    """Run prelaunch scanner and integrate results into creator registry"""
    
    print("="*60)
    print("PRELAUNCH INTELLIGENCE INTEGRATION")
    print("="*60)
    
    # Run prelaunch scanner with Helius resolution
    scanner = PreLaunchScanner()
    tokens = scanner.scan_all_sources(limit=limit, resolve_creators=True)
    
    print(f"PreLaunchScanner found {len(tokens)} tokens")
    
    # Load existing creator registry
    registry_path = Path("S:/kucoin-lane/data/creator_registry.json")
    with open(registry_path) as f:
        registry = json.load(f)
    
    # Defensive: ensure registry is a dict
    if not isinstance(registry, dict):
        logging.warning(f"Creator registry is not a dict (type: {type(registry).__name__}), starting fresh")
        registry = {}
    
    # Track statistics
    stats = {
        "tokens_scanned": len(tokens),
        "creators_resolved": 0,
        "new_creators_added": 0,
        "existing_creators_updated": 0,
        "high_confidence_tokens": 0,
        "social_links_found": 0,
        "tier_distribution": {}
    }
    
    # Process each token
    for token in tokens:
        creator = token.get("creator", "")
        mint = token.get("mint", "")
        tier = token.get("pre_launch_tier", "NOISE")
        social_links = token.get("social_links", {})
        community_score = token.get("community_score", 0)
        
        # Track tier distribution
        stats["tier_distribution"][tier] = stats["tier_distribution"].get(tier, 0) + 1
        
        if tier in ("HIGH_CONFIDENCE", "PROMISING"):
            stats["high_confidence_tokens"] += 1
        
        if social_links:
            stats["social_links_found"] += 1
        
        if not creator or creator == "unknown":
            continue
        
        stats["creators_resolved"] += 1
        
        if creator not in registry:
            # New creator - add to registry
            registry[creator] = {
                "creator_id": creator,
                "type": "wallet",
                "display_name": creator[:8] + "...",
                "first_seen": token.get("created_at", datetime.now(timezone.utc).isoformat()),
                "token_history": [{
                    "token": token.get("ticker", ""),
                    "timestamp": token.get("created_at", datetime.now(timezone.utc).isoformat()),
                    "composite_score": community_score,
                    "signal": "PRELAUNCH",
                    "factory": token.get("factory", "unknown"),
                    "mint": mint,
                    "pre_launch_tier": tier
                }],
                "performance_metrics": {
                    "avg_score": community_score,
                    "pre_launch_tier": tier
                },
                "social_links": social_links,
                "reputation_score": min(1.0, community_score * 0.3),
                "tags": []
            }
            stats["new_creators_added"] += 1
        else:
            # Existing creator - update history
            profile = registry[creator]
            profile["token_history"].append({
                "token": token.get("ticker", ""),
                "timestamp": token.get("created_at", datetime.now(timezone.utc).isoformat()),
                "composite_score": community_score,
                "signal": "PRELAUNCH",
                "factory": token.get("factory", "unknown"),
                "mint": mint,
                "pre_launch_tier": tier
            })
            
            # Update social links
            for platform, handle in social_links.items():
                if platform not in profile["social_links"]:
                    profile["social_links"][platform] = handle
            
            # Update reputation (simple average)
            scores = [t.get("composite_score", 0) for t in profile["token_history"]]
            profile["performance_metrics"]["avg_score"] = sum(scores) / len(scores)
            profile["reputation_score"] = min(1.0, profile["performance_metrics"]["avg_score"] * 0.3)
            
            stats["existing_creators_updated"] += 1
    
    # Save updated registry
    with open(registry_path, 'w') as f:
        json.dump(registry, f, indent=2)
    
    # Also create a mapping of mint -> creator for DEX signal enrichment
    mint_creator_map = {}
    for token in tokens:
        mint = token.get("mint", "")
        creator = token.get("creator", "")
        if mint and creator and creator != "unknown":
            mint_creator_map[mint] = creator
    
    # Save mint-creator map
    map_path = Path("S:/kucoin-lane/data/mint_creator_map.json")
    with open(map_path, 'w') as f:
        json.dump(mint_creator_map, f, indent=2)
    
    print(f"\nIntegration Complete:")
    print(f"  Tokens scanned: {stats['tokens_scanned']}")
    print(f"  Creators resolved: {stats['creators_resolved']}")
    print(f"  New creators added: {stats['new_creators_added']}")
    print(f"  Existing updated: {stats['existing_creators_updated']}")
    print(f"  High confidence tokens: {stats['high_confidence_tokens']}")
    print(f"  Social links found: {stats['social_links_found']}")
    print(f"  Tier distribution: {stats['tier_distribution']}")
    print(f"  Mint-creator mappings: {len(mint_creator_map)}")
    
    return stats

def enrich_dex_signals_with_prelaunch():
    """Enrich DEX signals using prelaunch mint-creator map"""
    
    # Load mint-creator map
    map_path = Path("S:/kucoin-lane/data/mint_creator_map.json")
    if not map_path.exists():
        print("No mint-creator map found. Run integrate_prelaunch_intelligence first.")
        return
    
    with open(map_path) as f:
        mint_creator_map = json.load(f)
    
    # Defensive: ensure mint_creator_map is a dict
    if not isinstance(mint_creator_map, dict):
        logging.warning(f"mint_creator_map is not a dict (type: {type(mint_creator_map).__name__}), skipping")
        return
    
    # Load DEX signals
    signals_path = Path("S:/kucoin-lane/data/latest_dex_signals.json")
    with open(signals_path) as f:
        signals = json.load(f)
    
    # Defensive: ensure signals is a list
    if not isinstance(signals, list):
        logging.warning(f"signals is not a list (type: {type(signals).__name__}), skipping")
        return
    
    # We need to get mint addresses for DEX signals
    # Since DexScreener doesn't provide mints in trending, we need to search
    # For now, let's create a pair -> mint mapping from prelaunch data
    
    # Load prelaunch tokens for pair->mint mapping
    prelaunch_path = Path("S:/kucoin-lane/data/prelaunch_tokens_latest.json")
    pair_mint_map = {}
    
    if prelaunch_path.exists():
        with open(prelaunch_path) as f:
            prelaunch_data = json.load(f)
        
        # Defensive: ensure prelaunch_data is a list
        if not isinstance(prelaunch_data, list):
            logging.warning(f"prelaunch_data is not a list (type: {type(prelaunch_data).__name__}), skipping")
            prelaunch_data = []
        
        for token in prelaunch_data:
            name = token.get("name", "")
            ticker = token.get("ticker", "")
            mint = token.get("mint", "")
            creator = token.get("creator", "")
            if mint and (name or ticker):
                pair_key = f"{ticker}/{name}".strip("/") if name else ticker
                pair_mint_map[pair_key] = {"mint": mint, "creator": creator}
    
    print(f"Pair-mint mappings available: {len(pair_mint_map)}")
    
    # Enrich signals
    enriched = 0
    for signal in signals:
        pair = signal.get("pair", "")
        # Try exact match
        if pair in pair_mint_map:
            signal["mint"] = pair_mint_map[pair]["mint"]
            signal["deployer"] = pair_mint_map[pair]["creator"]
            signal["creator_resolved"] = True
            enriched += 1
        else:
            # Try partial match on ticker
            ticker = pair.split("/")[0] if "/" in pair else pair
            for p, data in pair_mint_map.items():
                if ticker.lower() in p.lower() or p.lower() in ticker.lower():
                    signal["mint"] = data["mint"]
                    signal["deployer"] = data["creator"]
                    signal["creator_resolved"] = True
                    enriched += 1
                    break
    
    # Save enriched signals
    with open(signals_path, 'w') as f:
        json.dump(signals, f, indent=2)
    
    print(f"Enriched {enriched}/{len(signals)} DEX signals with creator data")
    return enriched

def save_prelaunch_tokens(tokens, limit=100):
    """Save prelaunch tokens for future enrichment"""
    prelaunch_path = Path("S:/kucoin-lane/data/prelaunch_tokens_latest.json")
    with open(prelaunch_path, 'w') as f:
        json.dump(tokens[:limit], f, indent=2)
    print(f"Saved {min(len(tokens), limit)} prelaunch tokens for enrichment")

if __name__ == "__main__":
    # Run full integration
    stats = integrate_prelaunch_intelligence(limit=100)
    
    # Save prelaunch tokens for DEX enrichment
    scanner = PreLaunchScanner()
    tokens = scanner.scan_all_sources(limit=100, resolve_creators=True)
    save_prelaunch_tokens(tokens)
    
    # Enrich DEX signals
    enrich_dex_signals_with_prelaunch()
    
    print("\n" + "="*60)
    print("FULL INTEGRATION COMPLETE")
    print("="*60)