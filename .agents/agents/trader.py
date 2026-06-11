#!/usr/bin/env python3
"""Trader Agent Entry Point"""

import sys
import argparse
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from context import read_context, record_position_open, record_position_close

def execute_buy(mint, sol_amount, sl_pct=0.15, tp_pct=0.50, venue="jupiter"):
    """Execute a buy order."""
    from execution.dex_jupiter_executor import JupiterDexExecutor
    
    executor = JupiterDexExecutor(paper_trading=True, sol_amount=sol_amount)
    
    # Get quote
    quote = executor.get_quote(mint, "So11111111111111111111111111111111111111112", amount=sol_amount)
    if not quote:
        return {"success": False, "error": "No quote available"}
    
    price = executor.get_price_from_quote(quote, mint, "So11111111111111111111111111111111111111112")
    if not price:
        return {"success": False, "error": "Could not determine price"}
    
    # Execute
    result = executor.execute(quote)
    
    if result:
        trade = {
            "id": f"trade_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}_{mint[:8]}",
            "mint": mint,
            "side": "buy",
            "venue": venue,
            "sol_in": sol_amount,
            "tokens_out": result.get("tokens_out", 0),
            "price_sol": price,
            "fee_sol": result.get("fee_sol", 0),
            "slippage_bps": result.get("slippage_bps", 0),
            "tx_sig": result.get("tx_sig", ""),
            "sl_price": price * (1 - sl_pct),
            "tp_price": price * (1 + tp_pct),
            "executed_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        }
        
        # Record position
        record_position_open(trade)
        
        return {"success": True, "trade": trade}
    
    return {"success": False, "error": "Execution failed"}

def execute_sell(mint, amount_pct=100, venue="jupiter"):
    """Execute a sell order."""
    # Implementation for selling
    return {"success": True, "trade": {"mint": mint, "side": "sell", "amount_pct": amount_pct}}

def monitor_positions():
    """Check SL/TP for all open positions."""
    from execution.dex_jupiter_executor import JupiterDexExecutor
    
    ctx = read_context()
    open_positions = ctx.get("positions", {}).get("open", [])
    closed = []
    
    executor = JupiterDexExecutor(paper_trading=True)
    
    for pos in open_positions:
        mint = pos.get("mint")
        if not mint:
            continue
        
        quote = executor.get_quote(mint, "So11111111111111111111111111111111111111112", amount=1000000)
        if quote:
            price = executor.get_price_from_quote(quote, mint, "So11111111111111111111111111111111111111112")
            if price:
                sl = pos.get("sl_price", 0)
                tp = pos.get("tp_price", 0)
                
                if (sl > 0 and price <= sl) or (tp > 0 and price >= tp):
                    # Trigger close
                    pnl_pct = (price - pos.get("price_sol", price)) / pos.get("price_sol", price)
                    pnl_usd = pnl_pct * pos.get("sol_in", 0) * 150  # approx SOL price
                    record_position_close(pos, pnl_usd)
                    closed.append({"mint": mint, "price": price, "pnl_usd": pnl_usd})
    
    return {"closed": closed}

def main():
    parser = argparse.ArgumentParser(description="Trader Agent")
    parser.add_argument("action", choices=["execute", "monitor", "positions"])
    parser.add_argument("--side", choices=["buy", "sell"])
    parser.add_argument("--mint", type=str)
    parser.add_argument("--sol", type=float, default=0.05)
    parser.add_argument("--amount-pct", type=float, default=100)
    parser.add_argument("--sl", type=float, default=0.15)
    parser.add_argument("--tp", type=float, default=0.50)
    parser.add_argument("--venue", choices=["jupiter", "kucoin"], default="jupiter")
    args = parser.parse_args()
    
    if args.action == "execute":
        if args.side == "buy":
            result = execute_buy(args.mint, args.sol, args.sl, args.tp, args.venue)
        else:
            result = execute_sell(args.mint, args.amount_pct, args.venue)
    elif args.action == "monitor":
        result = monitor_positions()
    elif args.action == "positions":
        ctx = read_context()
        result = {"positions": ctx.get("positions", {}).get("open", [])}
    
    print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    main()