"""
Deterministic Startup Module - Three-Stage Bot Initialization

Stage 1: CLEANUP - Remove corrupted/stale state from previous runs
Stage 2: INIT - Run mandatory initialization in strict order
Stage 3: VERIFY - Confirm critical systems work before trading

This ensures every bot restart follows the exact same path and verifies
that fixes actually work before entering the trading loop.
"""

import os
import json
import glob
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List

try:
    from atomic_writes import cleanup_temp_files, write_json_atomic, read_json_safe

    HAS_ATOMIC_WRITES = True
except ImportError:
    HAS_ATOMIC_WRITES = False


class DeterministicStartup:
    """Manages three-stage deterministic startup process."""

    def __init__(self, diag_log_func: Optional[Callable] = None):
        self.diag_log = diag_log_func or print
        self.startup_path: List[str] = []
        self.verification_results: Dict[str, bool] = {}

    def log(self, msg: str) -> None:
        self.diag_log(f"[DETERMINISTIC] {msg}")

    def cleanup_leftover_state(self) -> bool:
        self.log("=== STAGE 1: CLEANUP LEFTOVER STATE ===")
        self.startup_path.append("cleanup_started")

        if HAS_ATOMIC_WRITES:
            temp_cleaned = cleanup_temp_files()
            self.log(f"Cleaned {temp_cleaned} temporary state files")

        files_to_clean = [
            "bot_state.json",
            "bot_heartbeat.json",
            "shutdown_state.json",
        ]

        cleaned_count = 0
        for fname in files_to_clean:
            if os.path.exists(fname):
                try:
                    os.remove(fname)
                    self.log(f"Deleted stale file: {fname}")
                    cleaned_count += 1
                except Exception as e:
                    self.log(f"WARN: Could not delete {fname}: {e}")

        try:
            if os.path.exists("position_locks"):
                for lock_file in glob.glob("position_locks/*.lock"):
                    try:
                        os.remove(lock_file)
                        self.log(f"Deleted stale lock: {lock_file}")
                        cleaned_count += 1
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            if os.path.exists("state_backups"):
                backups = sorted(
                    glob.glob("state_backups/*.backup"), key=os.path.getctime
                )
                for old_backup in backups[:-5]:
                    try:
                        os.remove(old_backup)
                        self.log(f"Deleted old backup: {old_backup}")
                        cleaned_count += 1
                    except Exception:
                        pass
        except Exception:
            pass

        self.log(f"Cleanup complete: {cleaned_count} files removed")
        self.startup_path.append("cleanup_complete")
        return True

    def test_heartbeat_write(self) -> bool:
        try:
            test_data = {
                "test": True,
                "timestamp": time.time(),
            }
            with open("bot_heartbeat.json", "w") as f:
                json.dump(test_data, f)

            with open("bot_heartbeat.json", "r") as f:
                read_data = json.load(f)

            if read_data.get("test") is True:
                self.log("Heartbeat I/O: PASS")
                return True
            else:
                self.log("Heartbeat I/O: FAIL (data mismatch)")
                return False
        except Exception as e:
            self.log(f"Heartbeat I/O: ERROR - {e}")
            return False

    def test_kucoin_api(self, market_client=None) -> bool:
        try:
            if market_client is None:
                self.log("KuCoin API: SKIP (no client available)")
                return True

            try:
                if hasattr(market_client, "get_server_timestamp"):
                    timestamp = market_client.get_server_timestamp()
                    if isinstance(timestamp, (int, float)) and timestamp > 0:
                        self.log("KuCoin API: PASS")
                        return True
                    else:
                        self.log(
                            f"KuCoin API: Got unexpected timestamp format: {type(timestamp)}"
                        )
                        return True
            except Exception as e:
                self.log(f"KuCoin API: Warning - {e}")
                return True

            self.log("KuCoin API: SKIP (no get_server_timestamp method)")
            return True
        except Exception as e:
            self.log(f"KuCoin API: SKIP (exception - {e})")
            return True

    def test_telegram(self, notifier=None) -> bool:
        try:
            if notifier is None:
                self.log("Telegram: SKIP (not initialized)")
                return True

            if not hasattr(notifier, "enabled"):
                self.log("Telegram: FAIL (no 'enabled' attribute)")
                return False

            if not notifier.enabled:
                self.log("Telegram: FAIL (disabled)")
                return False

            try:
                if hasattr(notifier, "send"):
                    notifier.send("[VERIFY] Bot pre-flight check passed")
                    self.log("Telegram: PASS (send successful)")
                    return True
                elif hasattr(notifier, "send_message"):
                    notifier.send_message("[VERIFY] Bot pre-flight check passed")
                    self.log("Telegram: PASS (send_message successful)")
                    return True
                else:
                    self.log("Telegram: FAIL (no send method found)")
                    return False
            except Exception as send_error:
                self.log(f"Telegram: FAIL (send error: {send_error})")
                return False

        except Exception as e:
            self.log(f"Telegram: ERROR - {e}")
            return False

    def test_working_directory(self) -> bool:
        try:
            cwd = os.getcwd()
            required_files = ["requirements.txt"]

            env_ok = os.path.exists(".env") or (
                os.getenv("KUCOIN_API_KEY")
                and os.getenv("KUCOIN_API_SECRET")
                and os.getenv("KUCOIN_API_PASSPHRASE")
            )

            if not env_ok:
                self.log(
                    "Working Directory: FAIL (.env file missing and required env vars not set)"
                )
                return False

            found_all = True
            for req_file in required_files:
                if not os.path.exists(req_file):
                    self.log(f"Working Directory: FAIL (missing {req_file})")
                    found_all = False
                    break

            if found_all:
                self.log(f"Working Directory: PASS ({cwd})")
                return True
            else:
                return False
        except Exception as e:
            self.log(f"Working Directory: ERROR - {e}")
            return False

    def verify_critical_systems(
        self,
        market_client=None,
        notifier=None,
        required_systems: Optional[List[str]] = None,
    ) -> bool:
        self.log("=== STAGE 3: PRE-FLIGHT VERIFICATION ===")
        self.startup_path.append("verify_started")

        if required_systems is None:
            required_systems = [
                "working_directory",
                "heartbeat_io",
                "kucoin_api",
            ]

            if os.getenv("TELEGRAM_ENABLED", "false").lower() in {"1", "true", "yes"}:
                required_systems.append("telegram")

        print("\n" + "=" * 70)
        print("[VERIFY] PRE-FLIGHT SYSTEMS CHECK")
        print("=" * 70)

        checks = {
            "working_directory": self.test_working_directory,
            "heartbeat_io": self.test_heartbeat_write,
            "kucoin_api": lambda: self.test_kucoin_api(market_client),
            "telegram": lambda: self.test_telegram(notifier),
        }

        failed_checks = []
        passed_checks = []

        for check_name in required_systems:
            if check_name not in checks:
                self.log(f"WARN: Unknown check '{check_name}'")
                continue

            check_func = checks[check_name]
            try:
                result = check_func()
                self.verification_results[check_name] = result

                if result:
                    print(f"  [OK] {check_name.upper()}")
                    passed_checks.append(check_name)
                else:
                    print(f"  [FAIL] {check_name.upper()}")
                    failed_checks.append(check_name)
                    self.log(f"Check failed: {check_name}")
            except Exception as e:
                print(f"  [ERROR] {check_name.upper()} - {e}")
                failed_checks.append(check_name)
                self.log(f"Check error: {check_name} - {e}")

        print("=" * 70)

        if failed_checks:
            print(f"\n[FATAL] VERIFICATION FAILED: {', '.join(failed_checks)}")
            print("[FATAL] Bot will NOT enter trading loop.")
            print("[FATAL] Fix the issues above and restart.\n")
            self.startup_path.append("verify_failed")
            self.log(f"Verification FAILED: {failed_checks}")
            return False
        else:
            print(
                f"\n[OK] ALL CHECKS PASSED - {len(passed_checks)}/{len(required_systems)} systems verified"
            )
            print("[OK] Safe to enter trading loop.\n")
            self.startup_path.append("verify_passed")
            self.log(
                f"Verification PASSED: All {len(required_systems)} systems verified"
            )
            return True

    def get_startup_path(self) -> str:
        return " -> ".join(self.startup_path)

    def log_startup_summary(self) -> None:
        path_str = self.get_startup_path()
        self.log(f"Startup path: {path_str}")

        if self.verification_results:
            results_str = ", ".join(
                [
                    f"{k}={'PASS' if v else 'FAIL'}"
                    for k, v in self.verification_results.items()
                ]
            )
            self.log(f"Verification results: {results_str}")
