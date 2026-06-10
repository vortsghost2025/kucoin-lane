"""DEX executor for Solana pre-launch tokens via Jupiter aggregator.

This module provides a paper-trading mode for testing and a stub for live
Jupiter integration. Real swaps require:
- Jupiter quote endpoint (GET /quote)
- Jupiter swap endpoint (POST /swap)  
- Solana wallet signing (Phantom, Solflare, etc.)
"""

import json
import logging
import os
import time
import random
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("dex_jupiter")

JUPITER_QUOTE_URL = "https://api.jup.ag/swap/v1/quote"
JUPITER_SWAP_URL = "https://api.jup.ag/swap/v1/swap"

# Known token decimals for price calculation
TOKEN_DECIMALS = {
    "So11111111111111111111111111111111111111112": 9,  # WSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": 6,  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": 6,  # USDT
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xrnDawQKxgDcGxd": 5,  # BONK
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": 6,  # WIF
    "7dHbWX5oQyWb1D1KHPZnN3L7B4UW9EYWGGVcT1U9b8h": 6,  # JUP
}

# Rate limiting
_last_jupiter_call = 0.0
_jupiter_lock = None
try:
    import threading
    _jupiter_lock = threading.Lock()
except ImportError:
    pass


def is_valid_solana_mint(mint: str) -> bool:
    """Check if mint is a valid Solana address (not Ethereum)."""
    if not mint:
        return False
    if mint.startswith("0x"):
        return False
    if len(mint) < 32 or len(mint) > 44:
        return False
    # Basic base58 check
    try:
        import base58
        base58.b58decode(mint)
        return True
    except Exception:
        # If base58 not available, do basic check
        return all(c in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in mint)


def rate_limit_jupiter(min_interval: float = 0.2):
    """Rate limit Jupiter API calls."""
    global _last_jupiter_call
    if _jupiter_lock:
        with _jupiter_lock:
            now = time.time()
            elapsed = now - _last_jupiter_call
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            _last_jupiter_call = time.time()
    else:
        now = time.time()
        elapsed = now - _last_jupiter_call
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_jupiter_call = now


# SOL price cache (valid for 30 seconds)
_sol_price_cache = {"price": None, "timestamp": 0}
_sol_price_lock = None
try:
    import threading
    _sol_price_lock = threading.Lock()
except ImportError:
    pass


def get_sol_price_usd() -> float:
    """Get real SOL price in USD from Jupiter or fallback to CoinGecko."""
    global _sol_price_cache
    now = time.time()
    if _sol_price_lock:
        with _sol_price_lock:
            if _sol_price_cache["price"] and (now - _sol_price_cache["timestamp"] < 30):
                return _sol_price_cache["price"]
    else:
        if _sol_price_cache["price"] and (now - _sol_price_cache["timestamp"] < 30):
            return _sol_price_cache["price"]

    # Try Jupiter price API first (quote USDC/SOL)
    try:
        resp = requests.get(
            "https://api.jup.ag/swap/v1/quote",
            params={
                "inputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
                "outputMint": "So11111111111111111111111111111111111111112",  # SOL
                "amount": "1000000",  # 1 USDC
                "slippageBps": "50",
            },
            timeout=10,
        )
        data = resp.json()
        out_amount = float(data.get("outAmount", 0))
        if out_amount > 0:
            sol_per_usdc = out_amount / 1_000_000_000
            sol_price = 1.0 / sol_per_usdc
            _sol_price_cache = {"price": sol_price, "timestamp": time.time()}
            return sol_price
    except Exception:
        pass

    # Fallback to CoinGecko
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "solana", "vs_currencies": "usd"},
            timeout=10,
        )
        data = resp.json()
        sol_price = float(data.get("solana", {}).get("usd", 150.0))
        _sol_price_cache = {"price": sol_price, "timestamp": time.time()}
        return sol_price
    except Exception:
        return 150.0


class JupiterDexExecutor:
    """Execute DEX swaps on Solana via Jupiter aggregator."""

    def __init__(self, paper_trading: bool = True, sol_amount: float = 0.01):
        self.paper_trading = paper_trading
        self.sol_amount = sol_amount  # SOL to swap per trade
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "kucoin-lane/1.0"})

    def get_quote(
        self,
        input_mint: str,
        output_mint: str = "So11111111111111111111111111111111111111112",
        amount: Optional[float] = None,
        slippage_bps: int = 50,
        max_retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Get a quote from Jupiter with retry logic for rate limiting.

        Args:
            input_mint: Token mint address to swap FROM.
            output_mint: Token mint address to swap TO (default: WSOL).
            amount: Input amount in native units (SOL for WSOL, tokens for others).
            slippage_bps: Slippage tolerance in basis points (default: 50 = 0.5%).
            max_retries: Maximum retry attempts for 429 errors.
        """
        # Validate mint address
        if not is_valid_solana_mint(input_mint):
            logger.debug(f"Jupiter: invalid mint {input_mint}")
            return None
        if not is_valid_solana_mint(output_mint):
            logger.debug(f"Jupiter: invalid output mint {output_mint}")
            return None
        
        swap_amount = amount or self.sol_amount
        in_decimals = TOKEN_DECIMALS.get(input_mint, 9)
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(int(swap_amount * (10 ** in_decimals))),
            "slippageBps": str(slippage_bps),
        }
        
        for attempt in range(max_retries + 1):
            rate_limit_jupiter(0.2)  # 5 requests/second max
            try:
                resp = self.session.get(JUPITER_QUOTE_URL, params=params, timeout=10)
                
                if resp.status_code == 400:
                    logger.debug(f"Jupiter: token {input_mint} not tradable")
                    return None
                
                if resp.status_code == 429:
                    if attempt < max_retries:
                        wait_time = (2 ** attempt) * 0.5 + random.uniform(0, 0.5)
                        logger.warning(f"Jupiter rate limited (429), retry {attempt + 1}/{max_retries} in {wait_time:.1f}s")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.warning(f"Jupiter rate limited after {max_retries} retries")
                        return None
                
                resp.raise_for_status()
                return resp.json()
                
            except requests.exceptions.Timeout:
                if attempt < max_retries:
                    wait_time = (2 ** attempt) * 0.5
                    logger.warning(f"Jupiter timeout, retry {attempt + 1}/{max_retries} in {wait_time:.1f}s")
                    time.sleep(wait_time)
                    continue
                logger.warning(f"Jupiter timeout after {max_retries} retries")
                return None
                
            except Exception as e:
                logger.warning(f"Jupiter quote failed for {input_mint}: {e}")
                return None
        
        return None

    def get_price_from_quote(self, quote: Dict[str, Any], input_mint: str, output_mint: str) -> Optional[float]:
        """Extract price from Jupiter quote response.
        
        Returns: price of 1 input_mint in output_mint units.
        """
        try:
            in_amount = int(quote.get("inAmount", 0))
            out_amount = int(quote.get("outAmount", 0))
            if in_amount == 0 or out_amount == 0:
                return None
            in_decimals = TOKEN_DECIMALS.get(input_mint, 9)
            out_decimals = TOKEN_DECIMALS.get(output_mint, 9)
            in_units = in_amount / (10 ** in_decimals)
            out_units = out_amount / (10 ** out_decimals)
            return out_units / in_units
        except Exception as e:
            logger.warning(f"Failed to extract price from quote: {e}")
            return None

    def execute_swap(
        self,
        input_mint: str,
        output_mint: str = "So11111111111111111111111111111111111111112",
        amount: Optional[float] = None,
        direction: str = "buy",
    ) -> Dict[str, Any]:
        """Execute a swap via Jupiter.

        Args:
            input_mint: Token mint to swap FROM.
            output_mint: Token mint to swap TO (default: WSOL).
            amount: Input amount in native units.
            direction: "buy" (SOL -> token) or "sell" (token -> SOL).
        """
        if self.paper_trading:
            return self._paper_swap(input_mint, output_mint, amount, direction)

        # LIVE MODE (stub - requires Jupiter API key + Solana wallet signing)
        logger.warning("Live Jupiter swap not yet implemented - use paper mode")
        return {"success": False, "error": "Live mode not implemented"}

    def _paper_swap(
        self,
        input_mint: str,
        output_mint: str,
        amount: Optional[float] = None,
        direction: str = "buy",
    ) -> Dict[str, Any]:
        """Simulate a swap for paper trading using REAL Jupiter quotes for price discovery.
        
        Returns price as SOL per token (for consistent ledger accounting).
        """
        amount = amount or self.sol_amount
        
        wsol_mint = "So11111111111111111111111111111111111111112"
        
        if direction == "buy":
            # Buying token with SOL: quote WSOL -> token
            quote_input = wsol_mint
            quote_output = input_mint
            swap_amount = amount
        else:
            # Selling token for SOL: quote token -> WSOL
            quote_input = input_mint
            quote_output = wsol_mint
            swap_amount = amount
        
        quote = self.get_quote(quote_input, quote_output, swap_amount)
        price_sol_per_token = None
        estimated_output = 0.0
        
        if quote:
            # get_price_from_quote returns output_units / input_units
            raw_price = self.get_price_from_quote(quote, quote_input, quote_output)
            if raw_price:
                if direction == "buy":
                    # raw_price = token/SOL, we need SOL/token
                    price_sol_per_token = 1.0 / raw_price
                    estimated_output = amount / price_sol_per_token  # SOL / (SOL/token) = token
                else:
                    # raw_price = SOL/token (already correct)
                    price_sol_per_token = raw_price
                    estimated_output = amount * price_sol_per_token  # token * (SOL/token) = SOL
        
        if price_sol_per_token is None:
            logger.warning(f"Jupiter quote failed for {input_mint}, using paper fallback price")
            price_sol_per_token = self._fallback_paper_price(input_mint, quote_output)
            if direction == "buy":
                estimated_output = amount / price_sol_per_token
            else:
                estimated_output = amount * price_sol_per_token
            quote = {
                "source": "paper_fallback",
                "price_sol_per_token": price_sol_per_token,
            }
        
        return {
            "success": True,
            "txid": f"paper_{input_mint[:8]}_{os.urandom(4).hex()}",
            "input_mint": input_mint,
            "output_mint": output_mint,
            "input_amount": amount,
            "estimated_output": estimated_output,
            "price": price_sol_per_token,  # SOL per token
            "quote": quote,
            "direction": direction,
        }

    @staticmethod
    def _fallback_paper_price(input_mint: str, output_mint: str) -> float:
        """Deterministic offline SOL/token price for paper-only fallback."""
        if input_mint == output_mint:
            return 1.0
        seed = sum(ord(ch) for ch in str(input_mint)[:24])
        return max(0.000000001, ((seed % 1000) + 1) / 1_000_000_000)

    def run_cycle(
        self, buy_decisions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Process a list of BUY decisions through the DEX executor."""
        results = []
        for decision in buy_decisions:
            mint = decision.get("mint", "")
            symbol = decision.get("symbol", "?")
            score = decision.get("score", 0)

            if not mint:
                continue

            logger.info(f"Processing {symbol} ({mint[:8]}...) score={score}")
            # BUY: swap SOL -> token (mint)
            result = self.execute_swap(mint, direction="buy")
            result["symbol"] = symbol
            result["score"] = score
            results.append(result)

        return results
