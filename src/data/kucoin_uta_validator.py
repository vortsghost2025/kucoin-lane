"""
KuCoin Unified Account (UTA) Validator
Uses environment variables for credentials instead of hardcoded keys.
"""

import os
import time
import hmac
import hashlib
import base64
import logging
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)


class KuCoinUTAValidator:
    """Validates KuCoin Unified Account access and balance visibility."""

    def __init__(self) -> None:
        self.api_key = os.getenv("KUCOIN_API_KEY")
        self.api_secret = os.getenv("KUCOIN_API_SECRET")
        self.api_passphrase = os.getenv("KUCOIN_API_PASSPHRASE")
        self.base_url = "https://api.kucoin.com"
        self.timeout = 10

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret and self.api_passphrase)

    def _generate_signature(self, timestamp: str, method: str, endpoint: str) -> tuple:
        str_to_sign = f"{timestamp}{method}{endpoint}"

        hmac_obj = hmac.new(
            self.api_secret.encode(), str_to_sign.encode(), hashlib.sha256
        )
        signature = base64.b64encode(hmac_obj.digest()).decode()

        passphrase_hmac = hmac.new(
            self.api_secret.encode(), self.api_passphrase.encode(), hashlib.sha256
        )
        encrypted_passphrase = base64.b64encode(passphrase_hmac.digest()).decode()

        return signature, encrypted_passphrase

    def _make_request(self, method: str, endpoint: str) -> Dict[str, Any]:
        try:
            timestamp = str(int(time.time() * 1000))
            signature, encrypted_passphrase = self._generate_signature(
                timestamp, method, endpoint
            )

            headers = {
                "KC-API-KEY": self.api_key,
                "KC-API-SIGN": signature,
                "KC-API-TIMESTAMP": timestamp,
                "KC-API-PASSPHRASE": encrypted_passphrase,
                "KC-API-KEY-VERSION": "2",
                "Content-Type": "application/json",
            }

            url = f"{self.base_url}{endpoint}"
            response = requests.request(
                method, url, headers=headers, timeout=self.timeout
            )

            return {
                "status_code": response.status_code,
                "success": response.status_code == 200,
                "data": response.json() if response.text else {},
                "headers": dict(response.headers),
            }
        except requests.Timeout:
            return {"success": False, "error": "Request timeout", "status_code": 0}
        except requests.RequestException as e:
            return {"success": False, "error": str(e), "status_code": 0}
        except Exception as e:
            return {"success": False, "error": str(e), "status_code": 0}

    def validate_unified_account(self) -> Dict[str, Any]:
        endpoint = "/api/v1/accounts"
        result = self._make_request("GET", endpoint)

        return {
            "test": "Unified Account (Universal)",
            "endpoint": endpoint,
            "status_code": result.get("status_code"),
            "success": result.get("success"),
            "error": result.get("error"),
            "account_count": len(result.get("data", {}).get("data", []))
            if result.get("success")
            else 0,
        }

    def validate_ledgers(self) -> Dict[str, Any]:
        endpoint = "/api/v1/accounts/ledgers?currency=USDT"
        result = self._make_request("GET", endpoint)

        return {
            "test": "Account Ledgers (USDT)",
            "endpoint": endpoint,
            "status_code": result.get("status_code"),
            "success": result.get("success"),
            "error": result.get("error"),
            "ledger_count": len(result.get("data", {}).get("data", []))
            if result.get("success")
            else 0,
        }

    def validate_hf_accounts(self) -> Dict[str, Any]:
        endpoint = "/api/v1/accounts?type=trade-hf"
        result = self._make_request("GET", endpoint)

        return {
            "test": "HF Trade Account",
            "endpoint": endpoint,
            "status_code": result.get("status_code"),
            "success": result.get("success"),
            "error": result.get("error"),
            "account_count": len(result.get("data", {}).get("data", []))
            if result.get("success")
            else 0,
        }

    def validate_hf_v3(self) -> Dict[str, Any]:
        endpoint = "/api/v3/hf/accounts?type=trade"
        result = self._make_request("GET", endpoint)

        return {
            "test": "HF Trade Account (V3)",
            "endpoint": endpoint,
            "status_code": result.get("status_code"),
            "success": result.get("success"),
            "error": result.get("error"),
            "account_count": len(result.get("data", {}).get("data", []))
            if result.get("success")
            else 0,
        }

    def run_validation(self) -> Dict[str, Any]:
        print("\n" + "=" * 70)
        print("  KuCoin Unified Account (UTA) Validation")
        print("=" * 70)

        if not self.is_configured():
            print("\nCREDENTIALS NOT CONFIGURED")
            print("  Missing environment variables:")
            if not self.api_key:
                print("  - KUCOIN_API_KEY")
            if not self.api_secret:
                print("  - KUCOIN_API_SECRET")
            if not self.api_passphrase:
                print("  - KUCOIN_API_PASSPHRASE")
            print("\n  Set these environment variables to enable validation.")
            print("=" * 70 + "\n")

            return {
                "configured": False,
                "validation_results": [],
                "summary": "SKIPPED - Credentials not configured",
            }

        print("\nCredentials configured from environment variables")
        print("  Proceeding with Unified Account validation...\n")

        results = []
        tests = [
            ("Universal Account", self.validate_unified_account),
            ("Account Ledgers", self.validate_ledgers),
            ("HF Trading Account", self.validate_hf_accounts),
            ("HF Trading V3", self.validate_hf_v3),
        ]

        for test_name, test_func in tests:
            result = test_func()
            results.append(result)

            status_symbol = "PASS" if result["success"] else "FAIL"
            print(f"  [{status_symbol}] {result['test']}")
            print(f"    Endpoint: {result['endpoint']}")
            print(f"    Status Code: {result['status_code']}")

            if result["success"]:
                if "account_count" in result:
                    print(f"    Accounts Visible: {result['account_count']}")
                print(f"    Balance visibility: CONFIRMED")
            else:
                print(f"    Error: {result['error']}")
                if result["status_code"] == 401:
                    print(f"    Issue: Unauthorized (check credentials)")
                elif result["status_code"] == 403:
                    print(f"    Issue: Forbidden (check API permissions)")
            print()

        successful = sum(1 for r in results if r["success"])
        total = len(results)

        print("-" * 70)
        print(f"Validation Summary: {successful}/{total} tests passed")
        print("-" * 70)

        if successful == total:
            print("\nUNIFIED ACCOUNT READY FOR OPERATIONS")
            print("  All endpoints accessible")
            print("  Balance visibility confirmed")
            print("  API credentials valid")
            summary = "READY"
        elif successful > 0:
            print(f"\nPARTIAL SUCCESS ({successful}/{total} endpoints working)")
            print("  Some endpoints may be restricted or disabled")
            summary = "PARTIAL"
        else:
            print("\nVALIDATION FAILED")
            print("  No endpoints accessible")
            print("  Check credentials and API permissions")
            summary = "FAILED"

        print("=" * 70 + "\n")

        return {
            "configured": True,
            "validation_results": results,
            "summary": summary,
            "passed": successful,
            "total": total,
        }
