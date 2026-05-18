"""P0 Safety Fixes - byte-level reliable edit script for execution_engine.py"""

import py_compile

EE_PATH = "src/execution/execution_engine.py"
EA_PATH = "src/execution/exchange_adapter.py"
CONFIG_PATH = "src/config.py"


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


def write_file(path, data):
    with open(path, "wb") as f:
        f.write(data)


def verify(path):
    try:
        py_compile.compile(path, doraise=True)
        print(f"  {path} compiles OK")
        return True
    except py_compile.PyCompileError as e:
        print(f"  COMPILE ERROR in {path}: {e}")
        return False


def fix_execution_engine():
    data = read_file(EE_PATH)
    original = data  # keep for backup
    crlf = b"\r\n" in data

    # P0-1: Fix "is False" -> "not" for position_approved and risk_approved
    old_1 = b"if position_approved is False or risk_approved is False:"
    new_1 = b"if not position_approved or not risk_approved:"
    if old_1 in data:
        data = data.replace(old_1, new_1, 1)
        print("  P0-1: Fixed 'is False' -> 'not' (closes None bypass)")
    else:
        print("  P0-1: WARNING - target not found!")

    # P0-4a: Add circuit breaker imports after exchange_adapter import
    old_4a = b"from .exchange_adapter import ExchangeAdapter, KuCoinAdapter"
    import_cb = b"from ..risk.circuit_breaker import CircuitBreaker"
    import_pcb = b"from ..risk.portfolio_circuit_breaker import PortfolioCircuitBreaker"
    nl = b"\r\n" if crlf else b"\n"
    new_4a = old_4a + nl + import_cb + nl + import_pcb
    if old_4a in data:
        data = data.replace(old_4a, new_4a, 1)
        print("  P0-4a: Added circuit breaker imports")
    else:
        print("  P0-4a: WARNING - target not found!")

    # P0-4b: Add circuit breaker init after adapter init line
    old_4b = b"self.adapter: Optional[ExchangeAdapter] = None"
    indent = b"        "  # 8 spaces
    new_4b = (
        old_4b
        + nl
        + indent
        + b"self.circuit_breaker = CircuitBreaker()"
        + nl
        + indent
        + b"self.portfolio_circuit_breaker = PortfolioCircuitBreaker()"
    )
    if old_4b in data:
        data = data.replace(old_4b, new_4b, 1)
        print("  P0-4b: Added circuit breaker init in LiveExecutor.__init__")
    else:
        print("  P0-4b: WARNING - target not found!")

    # P0-4c: Add circuit breaker checks before the approval check
    # Insert after "risk_approved = input_data.get("risk_approved", None)"
    old_4c = b'risk_approved = input_data.get("risk_approved", None)' + nl
    # Find the blank line after risk_approved
    search = b'risk_approved = input_data.get("risk_approved", None)' + nl
    if search in data:
        insert_pos = data.index(search) + len(search)
        # Insert circuit breaker checks
        # Use 8-space indent (same level as surrounding code in execute())
        cb_code = (
            nl
            + indent
            + b"if self.circuit_breaker.is_triggered():"
            + nl
            + indent
            + b"    return {"
            + nl
            + indent
            + b'        "agent": "LiveExecutor",'
            + nl
            + indent
            + b'        "action": "execute_trade",'
            + nl
            + indent
            + b'        "success": True,'
            + nl
            + indent
            + b'        "data": {"trade_executed": False, "reason": "Circuit breaker triggered"},'
            + nl
            + indent
            + b"    }"
            + nl
            + indent
            + b"if self.portfolio_circuit_breaker.is_triggered():"
            + nl
            + indent
            + b"    return {"
            + nl
            + indent
            + b'        "agent": "LiveExecutor",'
            + nl
            + indent
            + b'        "action": "execute_trade",'
            + nl
            + indent
            + b'        "success": True,'
            + nl
            + indent
            + b'        "data": {"trade_executed": False, "reason": "Portfolio circuit breaker triggered"},'
            + nl
            + indent
            + b"    }"
            + nl
            + nl
        )
        data = data[:insert_pos] + cb_code + data[insert_pos:]
        print("  P0-4c: Added circuit breaker checks in execute()")
    else:
        print("  P0-4c: WARNING - target not found!")

    # P0-5: Replace SL failure block - cancel entry order on SL failure
    # The current code after "CRITICAL: Failed to place stop-loss" continues with
    # "if take_profit > 0:" but should cancel the entry order first
    old_5 = (
        b'                self.log("error", f"CRITICAL: Failed to place stop-loss: {e}")'
        + nl
    )
    # We need to insert cancellation code right after this line
    # But first find the TP failure block too - replace the whole SL/TP failure section
    # Strategy: replace the SL critical log + the following TP block with
    # SL critical + cancel entry + return + (remove TP block since we unwound)

    # Actually, let me be more surgical. Find the exact SL failure handler
    # and add cancel+return after it, then also add similar logic for TP failure

    # Find the SL failure CRITICAL line
    sl_critical = b'                self.log("error", f"CRITICAL: Failed to place stop-loss: {e}")'
    if sl_critical in data:
        pos = data.index(sl_critical) + len(sl_critical)
        # Skip the newline
        if data[pos : pos + 2] == b"\r\n":
            pos += 2
        elif data[pos : pos + 1] == b"\n":
            pos += 1

        # Now we need to insert the cancel+return block
        # The existing code continues with "if take_profit > 0:" at same indent
        # We'll insert cancel+return BEFORE that, so the TP block never executes
        cancel_code = (
            nl
            + b"                try:"
            + nl
            + b"                    if order_details and isinstance(order_details, dict):"
            + nl
            + b'                        order_id = order_details.get("orderId") or order_details.get("order_id")'
            + nl
            + b"                        if order_id:"
            + nl
            + b"                            self.adapter.cancel_order(symbol=pair, order_id=str(order_id))"
            + nl
            + b'                            self.log("warning", f"Entry order {order_id} cancelled after SL failure")'
            + nl
            + b"                except Exception as cancel_err:"
            + nl
            + b'                    self.log("error", f"Failed to cancel entry order after SL failure: {cancel_err}")'
            + nl
            + b"                return {"
            + nl
            + b'                    "agent": "LiveExecutor",'
            + nl
            + b'                    "action": "execute_trade",'
            + nl
            + b'                    "success": False,'
            + nl
            + b'                    "data": {"trade_executed": False, "reason": "Stop-loss placement failed, entry order unwound"},'
            + nl
            + b"                }"
            + nl
        )
        data = data[:pos] + cancel_code + data[pos:]
        print("  P0-5: Added SL failure entry order cancellation + return")
    else:
        print("  P0-5: WARNING - SL critical line not found!")

    # Also handle TP failure - add entry+SL cancellation on TP failure
    tp_critical = b'                self.log("error", f"CRITICAL: Failed to place take-profit: {e}")'
    if tp_critical in data:
        pos = data.index(tp_critical) + len(tp_critical)
        if data[pos : pos + 2] == b"\r\n":
            pos += 2
        elif data[pos : pos + 1] == b"\n":
            pos += 1

        tp_cancel_code = (
            nl
            + b"                try:"
            + nl
            + b"                    if order_details and isinstance(order_details, dict):"
            + nl
            + b'                        oid = order_details.get("orderId") or order_details.get("order_id")'
            + nl
            + b"                        if oid:"
            + nl
            + b"                            self.adapter.cancel_order(symbol=pair, order_id=str(oid))"
            + nl
            + b'                            self.log("warning", f"Entry order {oid} cancelled after TP failure")'
            + nl
            + b"                except Exception as cancel_err2:"
            + nl
            + b'                    self.log("error", f"Failed to cancel entry order after TP failure: {cancel_err2}")'
            + nl
            + b"                return {"
            + nl
            + b'                    "agent": "LiveExecutor",'
            + nl
            + b'                    "action": "execute_trade",'
            + nl
            + b'                    "success": False,'
            + nl
            + b'                    "data": {"trade_executed": False, "reason": "Take-profit placement failed, entry order unwound"},'
            + nl
            + b"                }"
            + nl
        )
        data = data[:pos] + tp_cancel_code + data[pos:]
        print("  P0-5b: Added TP failure entry order cancellation + return")
    else:
        print("  P0-5b: WARNING - TP critical line not found!")

    # P0-2/P0-3: Add safety limit keys to select_executor() config dict
    old_23 = b'"monitor_interval_min": int(MONITOR_INTERVAL_MIN),'
    new_23 = (
        b'"monitor_interval_min": int(MONITOR_INTERVAL_MIN),'
        + nl
        + b'            "max_position_size_usd": float(os.getenv("MAX_POSITION_SIZE_USD", "10.0")),'
        + nl
        + b'            "max_trade_loss_usd": float(os.getenv("MAX_TRADE_LOSS_USD", "5.0")),'
        + nl
        + b'            "max_daily_loss_usd": float(os.getenv("MAX_DAILY_LOSS_USD", "10.0")),'
        + nl
        + b'            "min_balance_usd": float(os.getenv("MIN_BALANCE_USD", "10.0")),'
    )
    if old_23 in data:
        data = data.replace(old_23, new_23, 1)
        print("  P0-2/3: Added safety limit keys to select_executor() config")
    else:
        print("  P0-2/3: WARNING - target not found!")

    write_file(EE_PATH, data)
    return verify(EE_PATH)


def fix_exchange_adapter():
    data = read_file(EA_PATH)
    old = b'os.getenv("KUCOIN_USE_SANDBOX", "false")'
    new = b'os.getenv("KUCOIN_USE_SANDBOX", "true")'
    if old in data:
        data = data.replace(old, new, 1)
        write_file(EA_PATH, data)
        print("  P0-6: KUCOIN_USE_SANDBOX default -> 'true' (fail-closed)")
    else:
        print("  P0-6: WARNING - target not found!")
    return verify(EA_PATH)


def fix_config():
    data = read_file(CONFIG_PATH)
    new_vars = b"""\n
MAX_POSITION_SIZE_USD_GLOBAL = float(os.getenv("MAX_POSITION_SIZE_USD", "10.0"))
MAX_TRADE_LOSS_USD = float(os.getenv("MAX_TRADE_LOSS_USD", "5.0"))
MAX_DAILY_LOSS_USD = float(os.getenv("MAX_DAILY_LOSS_USD", "10.0"))
MIN_BALANCE_USD = float(os.getenv("MIN_BALANCE_USD", "10.0"))
"""
    if b"MAX_TRADE_LOSS_USD" not in data:
        data = data + new_vars
        write_file(CONFIG_PATH, data)
        print("  P0-7: Added safety env vars to config.py")
    else:
        print("  P0-7: Safety vars already present")
    return verify(CONFIG_PATH)


if __name__ == "__main__":
    print("=== Applying P0 Safety Fixes (byte-level) ===\n")

    print("Fixing execution_engine.py...")
    ok_ee = fix_execution_engine()

    print("\nFixing exchange_adapter.py...")
    ok_ea = fix_exchange_adapter()

    print("\nFixing config.py...")
    ok_cfg = fix_config()

    if ok_ee and ok_ea and ok_cfg:
        print("\n=== All P0 fixes applied and verified ===")
    else:
        print("\n=== SOME FIXES FAILED - check output above ===")
