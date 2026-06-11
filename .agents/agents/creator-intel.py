#!/usr/bin/env python3
"""Creator Intel Agent Entry Point"""

import sys
import argparse
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from context import read_context, update_context

def resolve_creator(mint, use_helius=True):
    """Resolve creator wallet for a token mint."""
    # In production, this would call Helius API
    # For now, return mock data structure
    
    # Try to find in existing creator registry
    ctx = read_context()
    creator_reg = ctx.get("creator_registry", {})
    
    # Mock resolution - in reality would call Helius
    creator = {
        "wallet": f"creator_{mint[:8]}",
        "first_seen": "2026-01-15T10:30:00Z",
        "total_launches": 12,
        "reputation_score": 0.72,
        "is_alpha": True,
        "is_serial": True,
        "stats": {
            "win_rate": 0.65,
            "avg_roi": 3.4,
            "rug_rate": 0.09,
            "total_volume_sol": 145.2,
            "avg_launch_interval_hours": 72.5
        },
        "recent_launches": [
            {"mint": mint, "roi": 2.1, "at": "2026-06-10T19:11:25Z"}
        ]
    }
    
    # Update registry
    reg = ctx.get("creator_registry", {})
    if "profiles" not in reg:
        reg["profiles"] = {}
    reg["profiles"][creator["wallet"]] = creator
    if creator["is_alpha"]:
        if "alpha_creators" not in reg:
            reg["alpha_creators"] = []
        if creator["wallet"] not in reg["alpha_creators"]:
            reg["alpha_creators"].append(creator["wallet"])
    if creator["is_serial"]:
        if "serial_launchers" not in reg:
            reg["serial_launchers"] = []
        if creator["wallet"] not in reg["serial_launchers"]:
            reg["serial_launchers"].append(creator["wallet"])
    
    reg["total_creators"] = len(reg.get("profiles", {}))
    reg["last_resolved"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    
    update_context({"creator_registry": reg})
    
    return {"success": True, "creator": creator}

def bulk_resolve(mints, limit=50):
    """Bulk resolve creators for multiple mints."""
    results = []
    for mint in mints[:limit]:
        result = resolve_creator(mint)
        if result.get("success"):
            results.append(result["creator"])
    return results

def get_profile(wallet):
    """Get creator profile by wallet."""
    ctx = read_context()
    profiles = ctx.get("creator_registry", {}).get("profiles", {})
    if wallet in profiles:
        return {"success": True, "creator": profiles[wallet]}
    return {"success": False, "error": "Creator not found"}

def list_alphas(min_score=0.7):
    """List alpha creators above threshold."""
    ctx = read_context()
    profiles = ctx.get("creator_registry", {}).get("profiles", {})
    alphas = [
        c for c in profiles.values()
        if c.get("reputation_score", 0) >= min_score
    ]
    return {"success": True, "alphas": alphas, "count": len(alphas)}

def main():
    parser = argparse.ArgumentParser(description="Creator Intel Agent")
    parser.add_argument("action", choices=["resolve", "bulk", "profile", "alphas"])
    parser.add_argument("--mint", type=str)
    parser.add_argument("--wallet", type=str)
    parser.add_argument("--source", type=str)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--min-score", type=float, default=0.7)
    args = parser.parse_args()
    
    if args.action == "resolve":
        result = resolve_creator(args.mint)
    elif args.action == "bulk":
        # Would get mints from scan results
        ctx = read_context()
        mints = []
        for source, data in ctx.get("scan_results", {}).items():
            for token in data.get("tokens", []):
                mints.append(token.get("mint"))
        result = {"creators": bulk_resolve(mints, args.limit)}
    elif args.action == "profile":
        result = get_profile(args.wallet)
    elif args.action == "alphas":
        result = list_alphas(args.min_score)
    
    print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    main()