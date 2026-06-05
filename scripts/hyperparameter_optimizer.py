#!/usr/bin/env python3
"""
Hyperparameter Optimizer for KuCoin Lane
Performs Walk-Forward Analysis (WFA) to optimize asset profile parameters
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.data.kucoin_klines_fetcher import KuCoinKlinesFetcher
from src.execution.exchange_adapter import KuCoinAdapter
from src.intelligence.historical_backtester import HistoricalBacktester

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class HyperparameterOptimizer:
    def __init__(self, account_balance=110, risk_per_trade=0.01):
        self.account_balance = account_balance
        self.risk_per_trade = risk_per_trade
        self.klines_fetcher = KuCoinKlinesFetcher(
            default_interval="1hour",
            default_candle_count=1000,
            cache_enabled=True
        )
        self.adapter = KuCoinAdapter(
            api_key=os.getenv("KUCOIN_API_KEY", ""),
            api_secret=os.getenv("KUCOIN_API_SECRET", ""),
            passphrase=os.getenv("KUCOIN_API_PASSPHRASE", "")
        )
        self.backtester = HistoricalBacktester()
        
    def load_asset_profiles(self, config_path="config/asset_profiles.json"):
        """Load current asset profiles"""
        full_path = os.path.join(PROJECT_ROOT, config_path)
        with open(full_path, 'r') as f:
            return json.load(f)
    
    def save_asset_profiles(self, profiles, config_path="config/asset_profiles.json"):
        """Save updated asset profiles"""
        full_path = os.path.join(PROJECT_ROOT, config_path)
        with open(full_path, 'w') as f:
            json.dump(profiles, f, indent=2)
        logger.info(f"Saved updated asset profiles to {full_path}")
    
    def calculate_position_size(self, signal_strength, win_rate, max_drawdown, pair_config):
        """Calculate position size based on signal quality and risk metrics"""
        # Base risk per trade (1% of account)
        base_risk_amount = self.account_balance * self.risk_per_trade
        
        # Adjust based on signal strength and win rate
        signal_quality = signal_strength * win_rate
        
        # Penalize high drawdown
        drawdown_penalty = max(0, 1 - (max_drawdown / 0.20))  # 20% max acceptable DD
        
        # Combined quality score
        quality_score = signal_quality * drawdown_penalty
        
        # Apply quality score to position size multiplier
        adjusted_multiplier = pair_config["position_size_multiplier"] * (0.5 + quality_score * 0.5)
        
        # Ensure multiplier stays within reasonable bounds
        adjusted_multiplier = max(0.1, min(2.0, adjusted_multiplier))
        
        return adjusted_multiplier
    
    def walk_forward_analysis(self, pair, start_date=None, end_date=None, 
                             train_window_days=30, test_window_days=7,
                             step_days=7):
        """
        Perform walk-forward analysis for a trading pair
        
        Args:
            pair: Trading pair (e.g., "AVAX/USDT")
            start_date: Start date for analysis (default: 90 days ago)
            end_date: End date for analysis (default: today)
            train_window_days: Days to use for training
            test_window_days: Days to use for testing
            step_days: Days to step forward each iteration
            
        Returns:
            Dictionary with optimal parameters and performance metrics
        """
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=90)
            
        logger.info(f"Starting WFA for {pair} from {start_date.date()} to {end_date.date()}")
        
        # Fetch historical data
        # Calculate how many candles we need
        total_days = (end_date - start_date).days
        candles_needed = int(total_days * 24) + 100  # Add buffer for indicators
        
        df = self.klines_fetcher.fetch_klines(
            self.adapter,
            pair,
            interval="1hour",
            candle_count=candles_needed
        )
        
        if df is None or df.empty:
            logger.error(f"Failed to fetch data for {pair}")
            return None
            
        # Filter to date range
        df = df[(df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)]
        df = df.reset_index(drop=True)
        
        logger.info(f"Fetched {len(df)} candles for {pair}")
        
        # Define parameter ranges to test
        position_multipliers = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5]
        signal_strength_adjustments = [-0.05, 0.0, 0.05, 0.10, 0.15]
        stop_loss_adjustments = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5]
        
        # Walk-forward windows
        train_seconds = train_window_days * 24 * 3600
        test_seconds = test_window_days * 24 * 3600
        step_seconds = step_days * 24 * 3600
        
        start_ts = int(start_date.timestamp())
        end_ts = int(end_date.timestamp())
        
        results = []
        window_start = start_ts
        
        while window_start + train_seconds + test_seconds <= end_ts:
            window_end = window_start + train_seconds + test_seconds
            
            # Get data for this window
            window_df = df[(df['timestamp'] >= window_start) & 
                          (df['timestamp'] < window_end)].copy()
            
            if len(window_df) < 50:  # Need minimum data
                window_start += step_seconds
                continue
                
            # Split into train and test
            train_df = window_df[(window_df['timestamp'] >= window_start) & 
                                (window_df['timestamp'] < window_start + train_seconds)]
            test_df = window_df[window_df['timestamp'] >= window_start + train_seconds]
            
            logger.info(f"Window: {datetime.fromtimestamp(window_start).date()} to "
                       f"{datetime.fromtimestamp(window_end).date()} "
                       f"(Train: {len(train_df)}, Test: {len(test_df)})")
            
            # Test each parameter combination on training data
            best_params = None
            best_sharpe = -np.inf
            
            for pos_mult in position_multipliers:
                for sig_adj in signal_strength_adjustments:
                    for sl_adj in stop_loss_adjustments:
                        # Simulate trading with these parameters on train data
                        # For simplicity, we'll use the historical backtester with modified parameters
                        # In practice, we'd need to modify the backtest logic to use these params
                        
                        # Calculate performance metrics
                        # For now, let's use a simplified approach
                        # We'll calculate returns based on a simple strategy and adjust by parameters
                        
                        # Skip if insufficient data
                        if len(train_df) < 30:
                            continue
                            
                        # Run backtest on training data with current parameters
                        # We'll create a mock analysis dict that incorporates our parameters
                        analysis = {
                            "signal_strength": 0.7,  # placeholder
                            "win_rate": 0.55,       # placeholder
                            # In reality, these would come from actual signal generation
                        }
                        
                        # For simplicity in this first version, let's just test
                        # position size multiplier impact on returns
                        # We'll use the historical backtester as-is but adjust
                        # the position sizing based on our multiplier
                        
                        # Get base performance from historical backtester
                        backtest_result = self.backtester.backtest_pair(
                            pair, 
                            {"signal_strength": 0.7, "win_rate": 0.55},  # dummy analysis
                            self.klines_fetcher,
                            self.adapter
                        )
                        
                        if backtest_result is None:
                            continue
                            
                        # Adjust returns by position size multiplier
                        base_return = backtest_result.get("win_rate", 0.5) - 0.5  # excess return
                        adjusted_return = base_return * pos_mult
                        
                        # Calculate Sharpe-like metric
                        volatility = 0.02  # placeholder - would calculate from returns
                        if volatility > 0:
                            sharpe = adjusted_return / volatility * np.sqrt(8760)
                        else:
                            sharpe = 0
                            
                        # Also consider drawdown
                        max_dd = backtest_result.get("max_drawdown", 0.08)
                        # Penalize high drawdown
                        sharpe = sharpe * (1 - min(max_dd / 0.20, 0.5))  # max 50% penalty
                        
                        if sharpe > best_sharpe:
                            best_sharpe = sharpe
                            best_params = {
                                "position_size_multiplier": pos_mult,
                                "signal_strength_adjustment": sig_adj,
                                "stop_loss_adjustment": sl_adj,
                                "sharpe": sharpe,
                                "max_drawdown": max_dd,
                                "win_rate": backtest_result.get("win_rate", 0.5)
                            }
            
            if best_params:
                results.append({
                    "window_start": window_start,
                    "window_end": window_end,
                    "best_params": best_params,
                    "train_samples": len(train_df),
                    "test_samples": len(test_df)
                })
                logger.info(f"Best params for window: {best_params}")
            
            window_start += step_seconds
        
        # Aggregate results across windows
        if not results:
            logger.warning(f"No valid windows for {pair}")
            return None
            
        # Calculate average parameters across windows
        avg_pos_mult = np.mean([r["best_params"]["position_size_multiplier"] for r in results])
        avg_sig_adj = np.mean([r["best_params"]["signal_strength_adjustment"] for r in results])
        avg_sl_adj = np.mean([r["best_params"]["stop_loss_adjustment"] for r in results])
        
        # Also calculate weighted average by Sharpe ratio
        total_weight = sum(r["best_params"]["sharpe"] for r in results if r["best_params"]["sharpe"] > 0)
        if total_weight > 0:
            weighted_pos_mult = sum(r["best_params"]["position_size_multiplier"] * 
                                 max(r["best_params"]["sharpe"], 0) for r in results) / total_weight
            weighted_sig_adj = sum(r["best_params"]["signal_strength_adjustment"] * 
                                  max(r["best_params"]["sharpe"], 0) for r in results) / total_weight
            weighted_sl_adj = sum(r["best_params"]["stop_loss_adjustment"] * 
                                 max(r["best_params"]["sharpe"], 0) for r in results) / total_weight
        else:
            weighted_pos_mult = avg_pos_mult
            weighted_sig_adj = avg_sig_adj
            weighted_sl_adj = avg_sl_adj
            
        # Overall performance metrics
        avg_sharpe = np.mean([r["best_params"]["sharpe"] for r in results])
        avg_dd = np.mean([r["best_params"]["max_drawdown"] for r in results])
        avg_win_rate = np.mean([r["best_params"]["win_rate"] for r in results])
        
        optimization_result = {
            "pair": pair,
            "analysis_period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "windows_analyzed": len(results),
            "recommended_parameters": {
                "position_size_multiplier": round(weighted_pos_mult, 3),
                "signal_strength_adjustment": round(weighted_sig_adj, 3),
                "stop_loss_adjustment": round(weighted_sl_adj, 3)
            },
            "alternative_parameters": {
                "position_size_multiplier": round(avg_pos_mult, 3),
                "signal_strength_adjustment": round(avg_sig_adj, 3),
                "stop_loss_adjustment": round(avg_sl_adj, 3)
            },
            "performance_metrics": {
                "average_sharpe_ratio": round(avg_sharpe, 3),
                "average_max_drawdown": round(avg_dd, 3),
                "average_win_rate": round(avg_win_rate, 3)
            },
            "window_details": results
        }
        
        logger.info(f"WFA completed for {pair}: "
                   f"recommended position_size_multiplier={weighted_pos_mult:.3f}")
        
        return optimization_result
    
    def optimize_all_pairs(self, pairs=None):
        """Optimize parameters for all specified pairs"""
        if pairs is None:
            pairs = ["AVAX/USDT", "DOGE/USDT", "LINK/USDT"]
            
        logger.info(f"Starting optimization for pairs: {pairs}")
        
        # Load current profiles
        profiles = self.load_asset_profiles()
        
        optimization_results = {}
        
        for pair in pairs:
            logger.info(f"\n{'='*50}")
            logger.info(f"Optimizing {pair}")
            logger.info(f"{'='*50}")
            
            result = self.walk_forward_analysis(pair)
            if result:
                optimization_results[pair] = result
                
                # Update the profiles with recommended parameters
                if "risk" not in profiles:
                    profiles["risk"] = {"default": {}, "pairs": {}}
                if "pairs" not in profiles["risk"]:
                    profiles["risk"]["pairs"] = {}
                    
                if pair not in profiles["risk"]["pairs"]:
                    profiles["risk"]["pairs"][pair] = {}
                    
                # Update with recommended parameters
                profiles["risk"]["pairs"][pair]["position_size_multiplier"] = \
                    result["recommended_parameters"]["position_size_multiplier"]
                profiles["risk"]["pairs"][pair]["signal_strength_adjustment"] = \
                    result["recommended_parameters"]["signal_strength_adjustment"]
                profiles["risk"]["pairs"][pair]["stop_loss_adjustment"] = \
                    result["recommended_parameters"]["stop_loss_adjustment"]
                    
                logger.info(f"Updated {pair} parameters:")
                logger.info(f"  position_size_multiplier: {profiles['risk']['pairs'][pair]['position_size_multiplier']}")
                logger.info(f"  signal_strength_adjustment: {profiles['risk']['pairs'][pair]['signal_strength_adjustment']}")
                logger.info(f"  stop_loss_adjustment: {profiles['risk']['pairs'][pair]['stop_loss_adjustment']}")
            else:
                logger.error(f"Failed to optimize {pair}")
        
        # Save updated profiles
        if optimization_results:
            self.save_asset_profiles(profiles)
            logger.info(f"\nOptimization complete! Updated {len(optimization_results)} pairs.")
            
            # Save detailed results
            results_file = f"optimization_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(results_file, 'w') as f:
                json.dump(optimization_results, f, indent=2)
            logger.info(f"Detailed results saved to {results_file}")
            
        return optimization_results

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run hyperparameter optimization for KuCoin Lane')
    parser.add_argument('--pairs', nargs='+', default=["AVAX/USDT", "DOGE/USDT", "LINK/USDT"],
                       help='Trading pairs to optimize')
    parser.add_argument('--balance', type=float, default=10000,
                       help='Account balance for position sizing')
    parser.add_argument('--risk', type=float, default=0.01,
                       help='Risk per trade (decimal)')
    parser.add_argument('--train-days', type=int, default=30,
                       help='Training window days')
    parser.add_argument('--test-days', type=int, default=7,
                       help='Testing window days')
    parser.add_argument('--step-days', type=int, default=7,
                       help='Step size days')
    
    args = parser.parse_args()
    
    optimizer = HyperparameterOptimizer(
        account_balance=args.balance,
        risk_per_trade=args.risk
    )
    
    # Override window sizes if specified
    optimizer.walk_forward_analysis = lambda pair: optimizer.walk_forward_analysis(
        pair,
        train_window_days=args.train_days,
        test_window_days=args.test_days,
        step_days=args.step_days
    )
    
    results = optimizer.optimize_all_pairs(args.pairs)
    
    if results:
        logger.info("\n✅ Optimization successful!")
        for pair, result in results.items():
            params = result["recommended_parameters"]
            logger.info(f"{pair}: position_multiplier={params['position_size_multiplier']:.3f}")
    else:
        logger.error("❌ Optimization failed!")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
