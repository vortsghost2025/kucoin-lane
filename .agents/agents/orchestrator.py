#!/usr/bin/env python3
"""Pipeline Orchestrator Agent Entry Point"""

import sys
import argparse
import json
import time
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from context import read_context, write_context, update_context, increment_cycle, set_pipeline_status, get_cycle

def run_cycle(interval_min=15):
    """Run a single pipeline cycle."""
    cycle_num = increment_cycle()
    set_pipeline_status("running", last_cycle_started=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())
    
    print(f"Starting cycle #{cycle_num}", file=sys.stderr)
    
    # Check circuit breakers
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from context import check_circuit_breakers
    breakers = check_circuit_breakers()
    if breakers.get("global") or breakers.get("portfolio"):
        set_pipeline_status("paused", reason="circuit_breaker_tripped")
        return {"success": False, "error": "Circuit breaker tripped", "cycle": cycle_num}
    
    cycle_start = time.time()
    results = {}
    
    # Phase 1: Scan all DEX sources
    print(f"Cycle #{cycle_num}: Scanning DEX sources...", file=sys.stderr)
    scan_result = run_subprocess("dex-scanner", ["scan", "--source", "all", "--limit", "50"])
    results["scan"] = scan_result
    
    # Phase 2: Creator resolution
    print(f"Cycle #{cycle_num}: Resolving creators...", file=sys.stderr)
    creator_result = run_subprocess("creator-intel", ["bulk"])
    results["creator_resolution"] = creator_result
    
    # Phase 3: Risk assessment (done per-trade in trader)
    
    # Phase 4: Execution (handled by trader per-signal)
    
    # Phase 5: Monitoring
    print(f"Cycle #{cycle_num}: Monitoring...", file=sys.stderr)
    monitor_result = run_subprocess("monitor", ["health", "--full"])
    results["monitoring"] = monitor_result
    
    # Phase 6: SL/TP check
    trader_result = run_subprocess("trader", ["monitor"])
    results["sl_tp"] = trader_result
    
    cycle_duration = time.time() - cycle_start
    
    # Update pipeline stats
    ctx = read_context()
    pipeline = ctx.get("pipeline", {})
    pipeline["cycles_completed"] = pipeline.get("cycles_completed", 0) + 1
    pipeline["last_cycle_completed"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    pipeline["last_cycle_duration"] = cycle_duration
    
    # Update ledger stats
    ledger = ctx.get("positions", {})
    pipeline["total_pnl_usd"] = ledger.get("total_pnl_usd", 0)
    pipeline["win_rate"] = ledger.get("win_rate", 0)
    pipeline["open_trades"] = len(ledger.get("open", []))
    pipeline["total_trades"] = ledger.get("total_trades", 0)
    
    update_context({"pipeline": pipeline})
    
    # Save signal log
    save_signal_log(cycle_num, results)
    
    set_pipeline_status("idle", last_cycle_completed=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())
    
    return {"success": True, "cycle": cycle_num, "duration": cycle_duration, "results": results}

def run_subprocess(agent, args):
    """Run a sub-agent via subprocess."""
    try:
        result = subprocess.run(
            [sys.executable, f".agents/agents/{agent}.py"] + args,
            capture_output=True, text=True, timeout=60, cwd=Path(__file__).parent.parent.parent
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            return {"success": False, "error": result.stderr}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def save_signal_log(cycle_num, results):
    """Save cycle summary to signal log."""
    import os
    log_path = Path(__file__).parent.parent.parent / "data" / "signal_log.json"
    
    log_entry = {
        "cycle": cycle_num,
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "results": results
    }
    
    if log_path.exists():
        with open(log_path) as f:
            logs = json.load(f)
    else:
        logs = []
    
    logs.append(log_entry)
    logs = logs[-500:]  # Keep last 500
    
    with open(log_path, "w") as f:
        json.dump(logs, f, indent=2, default=str)

def run_continuous(interval_min=15, max_cycles=0):
    """Run continuous pipeline."""
    cycle = 0
    try:
        while max_cycles == 0 or cycle < max_cycles:
            result = run_cycle(interval_min)
            if not result.get("success"):
                print(f"Cycle failed: {result.get('error')}", file=sys.stderr)
            cycle += 1
            if max_cycles and cycle >= max_cycles:
                break
            print(f"Sleeping {interval_min} min...", file=sys.stderr)
            time.sleep(interval_min * 60)
    except KeyboardInterrupt:
        print("Shutdown requested", file=sys.stderr)

def get_status():
    """Get pipeline status."""
    ctx = read_context()
    return {
        "cycle": ctx.get("cycle", 0),
        "pipeline": ctx.get("pipeline", {}),
        "positions": ctx.get("positions", {}),
        "circuit_breakers": ctx.get("circuit_breakers", {}),
    }

def get_signal_log(limit=10):
    """Get recent signal log entries."""
    log_path = Path(__file__).parent.parent.parent / "data" / "signal_log.json"
    if not log_path.exists():
        return []
    with open(log_path) as f:
        logs = json.load(f)
    return logs[-limit:]

def main():
    parser = argparse.ArgumentParser(description="Pipeline Orchestrator Agent")
    parser.add_argument("action", choices=["run-cycle", "run-continuous", "status", "signal-log", "pause", "resume"])
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--cycles", type=int, default=10)
    args = parser.parse_args()
    
    if args.action == "run-cycle":
        result = run_cycle(args.interval)
    elif args.action == "run-continuous":
        run_continuous(args.interval, args.max_cycles)
        result = {"success": True}
    elif args.action == "status":
        result = get_status()
    elif args.action == "signal-log":
        result = {"logs": get_signal_log(args.cycles)}
    elif args.action == "pause":
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from context import set_pipeline_status
        set_pipeline_status("paused")
        result = {"success": True, "status": "paused"}
    elif args.action == "resume":
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from context import set_pipeline_status
        set_pipeline_status("idle")
        result = {"success": True, "status": "idle"}
    
    print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    main()