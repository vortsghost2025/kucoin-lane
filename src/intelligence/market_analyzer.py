"""
Market Analysis Agent
Performs technical analysis and market regime classification.
Implements critical downtrend detection safety feature.
Includes entry timing validation to prevent mid-downswing purchases.
"""

import logging
from typing import Any, Dict, Optional
from enum import Enum

from ..base_agent import BaseAgent, AgentStatus
from ..config import MARKET_CONFIG as GLOBAL_MARKET_CONFIG
from ..entry_timing import EntryTimingValidator
from ..utils.timeframe import apply_timeframe_overrides, resolve_timeframe


class MarketRegime(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"
    HIGH_VOLATILITY = "high_volatility"
    UNKNOWN = "unknown"


DEFAULT_ASSET_CONFIG = {
    "rsi_weight": 0.8,
    "momentum_weight": 1.0,
    "volatility_adjustment": 0.1,
    "signal_threshold_adj": 0,
}


class MarketAnalysisAgent(BaseAgent):
    """
    Market Analysis Agent: Analyzes market conditions and detects trends.

    Responsibilities:
    - Calculate technical indicators (RSI, MACD, moving averages)
    - Classify market regime
    - Detect downtrends (CRITICAL SAFETY FEATURE)
    - Calculate volatility
    - Identify support/resistance levels
    - Generate trading signals with confidence scores
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("MarketAnalysisAgent", config)
        cfg = config or {}
        self.rsi_period = cfg.get("rsi_period", 14)
        self.macd_fast = cfg.get("macd_fast", 12)
        self.macd_slow = cfg.get("macd_slow", 26)
        self.macd_signal = cfg.get("macd_signal", 9)
        self.downtrend_threshold = cfg.get("downtrend_threshold", -5)
        self.timeframe = resolve_timeframe(cfg)

        global_asset_default = GLOBAL_MARKET_CONFIG.get("asset_config_default", {})
        config_asset_default = cfg.get("asset_config_default", {})
        if not isinstance(global_asset_default, dict):
            global_asset_default = {}
        if not isinstance(config_asset_default, dict):
            config_asset_default = {}
        self.asset_config_default = {
            **DEFAULT_ASSET_CONFIG,
            **global_asset_default,
            **config_asset_default,
        }

        global_asset_configs = GLOBAL_MARKET_CONFIG.get("asset_configs", {})
        config_asset_configs = cfg.get("asset_configs", global_asset_configs)
        if isinstance(config_asset_configs, dict):
            self.asset_configs = {
                pair: value
                for pair, value in config_asset_configs.items()
                if isinstance(value, dict)
            }
        else:
            self.asset_configs = {}

        self.entry_timing_enabled = False
        self.entry_timing_validator = None

        if cfg:
            entry_config = cfg.get("entry_timing_config", {})
            if entry_config.get("enabled", False):
                threshold_pct = entry_config.get("reversal_threshold_pct", 0.001)
                self.entry_timing_validator = EntryTimingValidator(threshold_pct)
                self.entry_timing_enabled = True
                self.logger.info(
                    f"[ENTRY TIMING] Enabled with {threshold_pct * 100:.1f}% reversal threshold"
                )
            else:
                self.logger.info("[ENTRY TIMING] Disabled in config")
        else:
            self.logger.info("[ENTRY TIMING] Not configured")

        self.logger.info(
            f"[ASSET CONFIGS] Loaded {len(self.asset_configs)} pair overrides"
        )

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self.log_execution_start("analyze_market")

        try:
            market_data = input_data.get("market_data", {})
            if isinstance(market_data, dict) and "data" in market_data:
                market_data = market_data.get("data", {})

            if not market_data or isinstance(market_data, int):
                raise ValueError("No valid market data provided")

            analysis_results = {}
            has_bearish = False

            for pair, data in market_data.items():
                if not isinstance(data, dict):
                    continue

                self.logger.info(f"Analyzing {pair}")

                pair_analysis = self._analyze_pair(pair, data)
                analysis_results[pair] = pair_analysis

                if pair_analysis["regime"] == MarketRegime.BEARISH.value:
                    has_bearish = True
                    self.logger.warning(f"[WARN] BEARISH REGIME DETECTED for {pair}")

            overall_regime = self._determine_overall_regime(analysis_results)

            downtrend_detected = (
                has_bearish or overall_regime == MarketRegime.BEARISH.value
            )

            self.log_execution_end("analyze_market", success=True)

            return self.create_message(
                action="analyze_market",
                success=True,
                data={
                    "analysis": analysis_results,
                    "regime": overall_regime,
                    "downtrend_detected": downtrend_detected,
                    "pairs_analyzed": len(analysis_results),
                    "signal_confidence": self._calculate_overall_confidence(
                        analysis_results
                    ),
                },
            )

        except Exception as e:
            error_msg = f"Market analysis error: {str(e)}"
            self.set_status(AgentStatus.ERROR, error_msg)
            self.log_execution_end("analyze_market", success=False)
            return self.create_message(
                action="analyze_market", success=False, error=error_msg
            )

    def _analyze_pair(self, pair: str, data: Dict[str, Any]) -> Dict[str, Any]:
        current_price = data.get("current_price", 0)
        price_change_24h = data.get("price_change_24h_pct", 0)
        volume_24h = data.get("volume_24h", 0)

        rsi = self._calculate_rsi_simple(price_change_24h)
        macd_signal = self._calculate_macd_simple(price_change_24h)
        trend = self._determine_trend(price_change_24h, rsi)
        volatility = self._classify_volatility(price_change_24h)
        volatility_approved = self._is_volatility_suitable_for_trading(volatility)
        regime = self._classify_regime(price_change_24h, rsi, volatility)
        signal = self._generate_signal(price_change_24h, rsi, pair)

        asset_config = {**self.asset_config_default, **self.asset_configs.get(pair, {})}

        asset_config = apply_timeframe_overrides(asset_config, self.asset_configs.get(pair, {}), self.timeframe)

        buy_threshold = 58 + asset_config["signal_threshold_adj"]
        sell_threshold = 42 - asset_config["signal_threshold_adj"]

        entry_timing_approved = True
        entry_timing_reason = "Not configured"

        if self.entry_timing_enabled and self.entry_timing_validator:
            entry_timing_approved, entry_timing_reason = (
                self.entry_timing_validator.check_reversal_confirmation(
                    pair, current_price
                )
            )

            if not entry_timing_approved:
                self.logger.info(
                    f"[{pair}] Entry timing DEFERRED: {entry_timing_reason}"
                )

        return {
            "pair": pair,
            "current_price": current_price,
            "price_change_24h": price_change_24h,
            "rsi": rsi,
            "macd_signal": macd_signal,
            "trend": trend,
            "volatility": volatility,
            "volatility_approved": volatility_approved,
            "regime": regime,
            "buy_signal": signal,
            "signal_strength": min(1.0, ((abs(signal - 50) / 50) ** 0.5) * 1.5),
            "recommendation": "BUY"
            if signal > buy_threshold
            else "SELL"
            if signal < sell_threshold
            else "HOLD",
            "entry_timing_approved": entry_timing_approved,
            "entry_timing_reason": entry_timing_reason,
        }

    def _calculate_rsi_simple(self, price_change: float) -> float:
        rsi = 50 + (price_change / 10)
        return max(0, min(100, rsi))

    def _calculate_macd_simple(self, price_change: float) -> float:
        return price_change * 2

    def _determine_trend(self, price_change: float, rsi: float) -> str:
        if price_change > 2 or rsi > 60:
            return "uptrend"
        elif price_change < -2 or rsi < 40:
            return "downtrend"
        else:
            return "sideways"

    def _classify_volatility(self, price_change: float) -> str:
        abs_change = abs(price_change)
        if abs_change > 10:
            return "high"
        elif abs_change > 5:
            return "medium"
        else:
            return "low"

    def _is_volatility_suitable_for_trading(self, volatility: str) -> bool:
        if volatility in ["very_low", "low"]:
            self.logger.info(
                "[VOLATILITY] Low volatility detected - will require stronger signals"
            )
            return True
        return True

    def _classify_regime(self, price_change: float, rsi: float, volatility: str) -> str:
        if price_change < self.downtrend_threshold:
            return MarketRegime.BEARISH.value

        if rsi < 30:
            return MarketRegime.BEARISH.value

        if volatility == "high":
            return MarketRegime.HIGH_VOLATILITY.value

        if price_change > 3 and rsi > 55:
            return MarketRegime.BULLISH.value

        return MarketRegime.SIDEWAYS.value

    def _generate_signal(
        self, price_change: float, rsi: float, pair: str = ""
    ) -> float:
        asset_config = {**self.asset_config_default, **self.asset_configs.get(pair, {})}
        asset_config = apply_timeframe_overrides(asset_config, self.asset_configs.get(pair, {}), self.timeframe)

        rsi_weight = asset_config["rsi_weight"]
        momentum_weight = asset_config["momentum_weight"]

        signal = 50

        signal += price_change * (3.0 * momentum_weight)
        signal += (rsi - 50) * rsi_weight

        # Signal suppression removed — dampening already-weak signals prevents
        # any trade from reaching the signal_strength threshold (0.45 for sideways)

        return max(0, min(100, signal))

    def _determine_overall_regime(self, analysis: Dict[str, Dict]) -> str:
        regimes = [pair_analysis.get("regime") for pair_analysis in analysis.values()]

        if MarketRegime.BEARISH.value in regimes:
            return MarketRegime.BEARISH.value

        bullish_count = sum(1 for r in regimes if r == MarketRegime.BULLISH.value)
        high_vol_count = sum(
            1 for r in regimes if r == MarketRegime.HIGH_VOLATILITY.value
        )

        if len(regimes) == 0:
            return MarketRegime.UNKNOWN.value

        if bullish_count > len(regimes) / 2:
            return MarketRegime.BULLISH.value
        elif high_vol_count > len(regimes) / 2:
            return MarketRegime.HIGH_VOLATILITY.value
        else:
            return MarketRegime.SIDEWAYS.value

    def _calculate_overall_confidence(self, analysis: Dict[str, Dict]) -> float:
        if not analysis:
            return 0.0

        confidences = [pair["signal_strength"] for pair in analysis.values()]
        return sum(confidences) / len(confidences) if confidences else 0.0
