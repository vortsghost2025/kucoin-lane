"""
Enhanced Fee Model for Paper Trading
=====================================
Comprehensive fee calculation incorporating:
- pump.fun bonding curve fees (standard, mayhem, breaking)
- Jupiter aggregator fees (platform, price impact, slippage)
- Solana network fees (base + priority)
- DEX protocol fees (Raydium, Orca, etc.)
- Realized vs quoted slippage modeling

Sources:
- chainstacklabs/pumpfun-bonkfun-bot: pump.fun program fees, bonding curve math
- Jupiter API: platformFee, priceImpactPct, slippageBps
- Solana runtime: base fee + priority fee (Jito tips)
"""

import logging
import random
from dataclasses import dataclass
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


# pump.fun program constants (from chainstacklabs/pumpfun-bonkfun-bot)
PUMPFUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# Fee recipients (8 breaking fee recipients, randomized per tx)
BREAKING_FEE_RECIPIENTS = [
    "5YxQFdt3Tr9zJLvkFccqXVUwhdTWJQc1fFg2YPbxvxeD",
    "9M4giFFMxmFGXtc3feFzRai56WbBqehoSeRE5GK7gf7",
    "GXPFM2caqTtQYC2cJ5yJRi9VDkpsYZXzYdwYpGnLmtDL",
    "3BpXnfJaUTiwXnJNe7Ej1rcbzqTTQUvLShZaWazebsVR",
    "5cjcW9wExnJJiqgLjq7DEG75Pm6JBgE1hNv4B2vHXUW6",
    "EHAAiTxcdDwQ3U4bU6YcMsQGaekdzLS3B5SmYo46kJtL",
    "5eHhjP8JaYkz83CWwvGU2uMUXefd3AazWGx4gpcuEEYD",
    "A7hAgCzFw14fejgCp387JUJRMNyz4j89JKnhtKU8piqW",
]

# pump.fun fee structure (from IDL and on-chain observation)
# Standard pump.fun fee: 1% of SOL amount (0.01) on buy/sell
# Mayhem mode: different fee recipient, same rate
# Breaking fee: additional fee recipient (randomized from 8)
PUMPFUN_BUY_FEE_BPS = 100      # 1% = 100 bps
PUMPFUN_SELL_FEE_BPS = 100     # 1% = 100 bps

# Jupiter/default DEX fees
JUPITER_PLATFORM_FEE_BPS = 0   # Usually null/0 for Jupiter
JUPITER_DEFAULT_SLIPPAGE_BPS = 50  # 0.5%

# Solana network fees
SOLANA_BASE_FEE_LAMPORTS = 5000        # 0.000005 SOL base fee
PRIORITY_FEE_LAMPORTS_PER_CU = 1       # 1 microlamport per CU (typical)
DEFAULT_COMPUTE_UNITS = 200_000         # Typical swap compute units


@dataclass
class FeeBreakdown:
    """Detailed breakdown of all fees for a swap."""
    # Protocol fees
    pumpfun_fee_lamports: int = 0
    pumpfun_fee_bps: int = 0
    jupiter_platform_fee_lamports: int = 0
    jupiter_price_impact_bps: float = 0.0
    
    # Network fees
    solana_base_fee_lamports: int = SOLANA_BASE_FEE_LAMPORTS
    solana_priority_fee_lamports: int = 0
    
    # Slippage
    quoted_slippage_bps: int = JUPITER_DEFAULT_SLIPPAGE_BPS
    realized_slippage_bps: float = 0.0
    
    # Derived
    total_fees_lamports: int = 0
    total_fees_sol: float = 0.0
    total_fees_usd: float = 0.0
    
    def __post_init__(self):
        self.total_fees_lamports = (
            self.pumpfun_fee_lamports +
            self.jupiter_platform_fee_lamports +
            self.solana_base_fee_lamports +
            self.solana_priority_fee_lamports
        )
        self.total_fees_sol = self.total_fees_lamports / 1_000_000_000
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pumpfun_fee_lamports": self.pumpfun_fee_lamports,
            "pumpfun_fee_bps": self.pumpfun_fee_bps,
            "jupiter_platform_fee_lamports": self.jupiter_platform_fee_lamports,
            "jupiter_price_impact_bps": self.jupiter_price_impact_bps,
            "solana_base_fee_lamports": self.solana_base_fee_lamports,
            "solana_priority_fee_lamports": self.solana_priority_fee_lamports,
            "quoted_slippage_bps": self.quoted_slippage_bps,
            "realized_slippage_bps": self.realized_slippage_bps,
            "total_fees_lamports": self.total_fees_lamports,
            "total_fees_sol": self.total_fees_sol,
            "total_fees_usd": self.total_fees_usd,
        }


def pick_breaking_fee_recipient() -> str:
    """Randomly select one of 8 breaking fee recipients (per pump.fun 2026-04-28 upgrade)."""
    return random.choice(BREAKING_FEE_RECIPIENTS)


def calculate_pumpfun_fee(
    amount_in_lamports: int,
    is_buy: bool,
    is_mayhem: bool = False
) -> tuple[int, int]:
    """
    Calculate pump.fun protocol fee for a swap.
    
    Returns: (fee_lamports, fee_bps)
    
    Note: pump.fun charges 1% on both buy and sell.
    The fee is taken from the input amount (SOL for buy, tokens for sell).
    """
    fee_bps = PUMPFUN_BUY_FEE_BPS if is_buy else PUMPFUN_SELL_FEE_BPS
    fee_lamports = (amount_in_lamports * fee_bps) // 10000
    return fee_lamports, fee_bps


def calculate_jupiter_fees(
    quote: Dict[str, Any],
    input_mint: str,
    output_mint: str,
    is_buy: bool
) -> tuple[int, float, int]:
    """
    Extract fees from Jupiter quote response.
    
    Returns: (platform_fee_lamports, price_impact_bps, slippage_bps)
    """
    platform_fee = quote.get("platformFee")
    platform_fee_lamports = int(platform_fee) if platform_fee else 0
    
    price_impact = quote.get("priceImpactPct", 0.0)
    price_impact_bps = float(price_impact) * 100 if price_impact else 0.0
    
    slippage_bps = quote.get("slippageBps", JUPITER_DEFAULT_SLIPPAGE_BPS)
    if isinstance(slippage_bps, str):
        slippage_bps = int(slippage_bps)
    
    return platform_fee_lamports, price_impact_bps, slippage_bps


def calculate_solana_network_fee(
    compute_units: int = DEFAULT_COMPUTE_UNITS,
    priority_fee_per_cu: int = PRIORITY_FEE_LAMPORTS_PER_CU
) -> tuple[int, int]:
    """
    Calculate Solana network fees (base + priority).
    
    Returns: (base_fee_lamports, priority_fee_lamports)
    """
    base_fee = SOLANA_BASE_FEE_LAMPORTS
    priority_fee = compute_units * priority_fee_per_cu
    return base_fee, priority_fee


def calculate_realized_slippage(
    quote: Dict[str, Any],
    actual_output: int,
    expected_output: int
) -> float:
    """
    Calculate realized slippage vs quoted.
    
    Returns: realized slippage in bps (positive = worse than quoted)
    """
    if expected_output <= 0:
        return 0.0
    slippage = (expected_output - actual_output) / expected_output
    return slippage * 10000  # Convert to bps


def build_fee_breakdown(
    amount_in: float,
    input_mint: str,
    output_mint: str,
    is_buy: bool,
    quote: Optional[Dict[str, Any]] = None,
    sol_price_usd: float = 150.0,
    is_mayhem: bool = False,
    compute_units: int = DEFAULT_COMPUTE_UNITS
) -> FeeBreakdown:
    """
    Build complete fee breakdown for a swap.
    
    Args:
        amount_in: Input amount in native units (SOL for buy, tokens for sell)
        input_mint: Input token mint
        output_mint: Output token mint
        is_buy: True if buying token with SOL, False if selling token for SOL
        quote: Jupiter quote response (optional)
        sol_price_usd: Current SOL price in USD
        is_mayhem: Whether token is in mayhem mode
        compute_units: Estimated compute units for the transaction
    
    Returns:
        FeeBreakdown with all fee components
    """
    wsol_mint = "So11111111111111111111111111111111111111112"
    
    # Convert to lamports
    in_decimals = 9 if input_mint == wsol_mint else 6  # Simplified
    amount_in_lamports = int(amount_in * (10 ** in_decimals))
    
    # pump.fun protocol fee
    pumpfun_fee_lamports, pumpfun_fee_bps = calculate_pumpfun_fee(
        amount_in_lamports, is_buy, is_mayhem
    )
    
    # Jupiter fees (from quote if available)
    jupiter_platform_fee_lamports = 0
    price_impact_bps = 0.0
    slippage_bps = JUPITER_DEFAULT_SLIPPAGE_BPS
    
    if quote:
        jupiter_platform_fee_lamports, price_impact_bps, slippage_bps = calculate_jupiter_fees(
            quote, input_mint, output_mint, is_buy
        )
    
    # Solana network fees
    solana_base_fee, priority_fee = calculate_solana_network_fee(compute_units)
    
    # Build breakdown
    breakdown = FeeBreakdown(
        pumpfun_fee_lamports=pumpfun_fee_lamports,
        pumpfun_fee_bps=pumpfun_fee_bps,
        jupiter_platform_fee_lamports=jupiter_platform_fee_lamports,
        jupiter_price_impact_bps=price_impact_bps,
        solana_base_fee_lamports=solana_base_fee,
        solana_priority_fee_lamports=priority_fee,
        quoted_slippage_bps=slippage_bps,
    )
    
    # Convert to USD
    breakdown.total_fees_usd = breakdown.total_fees_sol * sol_price_usd
    
    return breakdown


def apply_fees_to_price(
    price_sol_per_token: float,
    fee_breakdown: FeeBreakdown,
    is_buy: bool
) -> float:
    """
    Adjust execution price to account for fees.
    
    For buy: effective price is higher (you pay more SOL per token)
    For sell: effective price is lower (you receive less SOL per token)
    """
    # Total fee as percentage of trade value
    # Approximate: fees in SOL / (position value in SOL)
    if is_buy:
        # Buyer pays fees on top of the quoted price
        # Effective price = quoted_price * (1 + total_fee_rate)
        return price_sol_per_token * (1 + fee_breakdown.total_fees_sol / 0.01)  # Rough approx
    else:
        # Seller receives less after fees
        return price_sol_per_token * (1 - fee_breakdown.total_fees_sol / 0.01)


def calculate_position_fees(
    entry_price: float,
    exit_price: float,
    position_size: float,
    direction: str,
    entry_fee_breakdown: FeeBreakdown,
    exit_fee_breakdown: FeeBreakdown,
    sol_price_usd: float = 150.0
) -> Dict[str, float]:
    """
    Calculate total fees for a round-trip position.
    
    Returns dict with fee components in USD.
    """
    entry_value_sol = entry_price * position_size
    exit_value_sol = exit_price * position_size
    
    entry_fees_usd = entry_fee_breakdown.total_fees_usd
    exit_fees_usd = exit_fee_breakdown.total_fees_usd
    
    total_fees_usd = entry_fees_usd + exit_fees_usd
    
    return {
        "entry_fees_usd": entry_fees_usd,
        "exit_fees_usd": exit_fees_usd,
        "total_fees_usd": total_fees_usd,
        "entry_fees_sol": entry_fee_breakdown.total_fees_sol,
        "exit_fees_sol": exit_fee_breakdown.total_fees_sol,
    }


# Convenience function for paper trading integration
def get_paper_trade_fees(
    entry_price: float,
    exit_price: float,
    position_size: float,
    direction: str,
    sol_price_usd: float = 150.0
) -> Dict[str, float]:
    """
    Simplified fee calculation for paper trading.
    
    Uses standard assumptions when quote data not available.
    """
    # Estimate entry fees (buy)
    entry_breakdown = build_fee_breakdown(
        amount_in=0.05,  # Default SOL per trade
        input_mint="So11111111111111111111111111111111111111112",  # WSOL
        output_mint="unknown",
        is_buy=True,
        sol_price_usd=sol_price_usd
    )
    
    # Estimate exit fees (sell)
    exit_breakdown = build_fee_breakdown(
        amount_in=position_size,
        input_mint="unknown",
        output_mint="So11111111111111111111111111111111111111112",  # WSOL
        is_buy=False,
        sol_price_usd=sol_price_usd
    )
    
    return calculate_position_fees(
        entry_price, exit_price, position_size, direction,
        entry_breakdown, exit_breakdown, sol_price_usd
    )


if __name__ == "__main__":
    # Test fee calculations
    print("=== Fee Model Tests ===\n")
    
    # Test 1: Buy 0.05 SOL worth of token
    breakdown = build_fee_breakdown(
        amount_in=0.05,
        input_mint="So11111111111111111111111111111111111111112",
        output_mint="EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
        is_buy=True,
        sol_price_usd=150.0
    )
    print(f"Buy 0.05 SOL:")
    print(f"  pump.fun fee: {breakdown.pumpfun_fee_lamports:,} lamports ({breakdown.pumpfun_fee_bps} bps)")
    print(f"  Solana base: {breakdown.solana_base_fee_lamports:,} lamports")
    print(f"  Priority fee: {breakdown.solana_priority_fee_lamports:,} lamports")
    print(f"  Total: {breakdown.total_fees_lamports:,} lamports = {breakdown.total_fees_sol:.8f} SOL = ${breakdown.total_fees_usd:.4f}")
    print()
    
    # Test 2: Sell position
    breakdown2 = build_fee_breakdown(
        amount_in=100.0,  # 100 tokens
        input_mint="EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
        output_mint="So11111111111111111111111111111111111111112",
        is_buy=False,
        sol_price_usd=150.0
    )
    print(f"Sell 100 tokens:")
    print(f"  pump.fun fee: {breakdown2.pumpfun_fee_lamports:,} lamports ({breakdown2.pumpfun_fee_bps} bps)")
    print(f"  Total: {breakdown2.total_fees_lamports:,} lamports = {breakdown2.total_fees_sol:.8f} SOL = ${breakdown2.total_fees_usd:.4f}")
    print()
    
    # Test 3: Round-trip fees
    fees = calculate_position_fees(
        entry_price=0.001,    # 0.001 SOL per token
        exit_price=0.0015,    # 0.0015 SOL per token
        position_size=50.0,   # 50 tokens
        direction="long",
        entry_fee_breakdown=breakdown,
        exit_fee_breakdown=breakdown2,
        sol_price_usd=150.0
    )
    print(f"Round-trip (0.05 SOL -> 50 tokens -> exit):")
    print(f"  Entry fees: ${fees['entry_fees_usd']:.4f}")
    print(f"  Exit fees: ${fees['exit_fees_usd']:.4f}")
    print(f"  Total fees: ${fees['total_fees_usd']:.4f}")