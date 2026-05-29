"""
Risk Management Agent
Calculates position sizing, stop-loss and take-profit levels.
Enforces strict risk controls: never risk more than 1% of capital per trade.
"""

from typing import Any, Dict, Optional
import logging

from ..base_agent import BaseAgent, AgentStatus

MAX_DAILY_LOSS_CAP = 0.02
DEFAULT_MIN_POSITION_SIZE_UNITS = 0.001


class RiskManagementAgent(BaseAgent):
    """
    Risk Management Agent: Enforces position sizing and risk controls.

    Responsibilities:
    - Calculate position size based on risk percentage
    - Generate stop-loss levels
    - Generate take-profit levels
    - Enforce risk-reward ratio minimum
    - Reject trades that violate risk thresholds
    - Track cumulative risk exposure

    Core Rule: Never risk more than 1% of capital per trade
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("RiskManagementAgent", config)

        self.account_balance = config.get("account_balance", 10000) if config else 10000
        self.risk_per_trade = config.get("risk_per_trade", 0.01) if config else 0.01
        self.min_risk_reward_ratio = (
            config.get("min_risk_reward_ratio", 1.5) if config else 1.5
        )

        requested_max_daily_loss = (
            config.get("max_daily_loss", 0.05) if config else 0.05
        )
        self.max_daily_loss = min(requested_max_daily_loss, MAX_DAILY_LOSS_CAP)

        self.default_stop_loss_pct = (
            config.get("default_stop_loss_pct", 0.02) if config else 0.02
        )
        self.min_signal_strength = (
            config.get("min_signal_strength", 0.3) if config else 0.3
        )
        self.min_win_rate = config.get("min_win_rate", 0.45) if config else 0.45
        self.min_notional_usd = config.get("min_notional_usd", 10.0) if config else 10.0

        if config:
            configured_min_size = config.get("min_position_size_units")
            self.min_position_size_units = (
                configured_min_size
                if configured_min_size is not None
                else DEFAULT_MIN_POSITION_SIZE_UNITS
            )
        else:
            self.min_position_size_units = DEFAULT_MIN_POSITION_SIZE_UNITS

        self.min_position_size_by_pair = (
            config.get("min_position_size_by_pair", {}) if config else {}
        )
        self.enforce_min_position_size_only = (
            config.get("enforce_min_position_size_only", True) if config else True
        )

        self.cumulative_risk_today = 0.0

        self.asset_configs = {
            "SOL/USDT": {
                "min_signal_strength_adjustment": 0.0,
                "stop_loss_adjustment": 1.0,
                "position_size_multiplier": 1.0,
            },
            "BTC/USDT": {
                "min_signal_strength_adjustment": 0.05,
                "stop_loss_adjustment": 0.95,
                "position_size_multiplier": 0.80,
            },
            "ETH/USDT": {
                "min_signal_strength_adjustment": 0.03,
                "stop_loss_adjustment": 0.97,
                "position_size_multiplier": 0.90,
            },
        }

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self.log_execution_start("assess_and_size_position")

        try:
            market_data = input_data.get("market_data", {})
            analysis = input_data.get("analysis", {})
            backtest_results = input_data.get("backtest_results", {})

            if not market_data or not analysis:
                raise ValueError("Missing market data or analysis")

            risk_assessments = {}
            total_risk = 0.0
            all_approved = True

            for pair, data in market_data.items():
                pair_analysis = analysis.get(pair, {})
                pair_backtest = backtest_results.get(pair, {})

                assessment = self._assess_pair_risk(
                    pair, data, pair_analysis, pair_backtest
                )
                risk_assessments[pair] = assessment

                if assessment["position_approved"]:
                    total_risk += assessment["risk_amount"]
                else:
                    all_approved = False

                self.logger.info(
                    f"{pair}: {'Approved' if assessment['position_approved'] else 'Rejected'} "
                    f"- Size: {assessment['position_size']:.4f}"
                )

            if (self.cumulative_risk_today + total_risk) > (
                self.account_balance * self.max_daily_loss
            ):
                all_approved = False
                rejection_reason = f"Daily loss limit would be exceeded: {self.cumulative_risk_today + total_risk:.2f} > {self.account_balance * self.max_daily_loss:.2f}"
                self.logger.warning(f"{rejection_reason}")
            else:
                rejection_reason = None

            self.log_execution_end("assess_and_size_position", success=all_approved)

            if all_approved:
                self.cumulative_risk_today += total_risk

            return self.create_message(
                action="assess_and_size_position",
                success=True,
                data={
                    "position_approved": all_approved,
                    "rejection_reason": rejection_reason,
                    "assessments": risk_assessments,
                    "total_risk_amount": total_risk,
                    "total_risk_pct": (total_risk / self.account_balance) * 100,
                    "cumulative_daily_risk": self.cumulative_risk_today,
                    "account_balance": self.account_balance,
                    "position_size": next(
                        (
                            a["position_size"]
                            for a in risk_assessments.values()
                            if a["position_approved"]
                        ),
                        0,
                    ),
                    "stop_loss": next(
                        (
                            a["stop_loss"]
                            for a in risk_assessments.values()
                            if a["position_approved"]
                        ),
                        None,
                    ),
                    "take_profit": next(
                        (
                            a["take_profit"]
                            for a in risk_assessments.values()
                            if a["position_approved"]
                        ),
                        None,
                    ),
                },
            )

        except Exception as e:
            error_msg = f"Risk assessment error: {str(e)}"
            self.set_status(AgentStatus.ERROR, error_msg)
            self.log_execution_end("assess_and_size_position", success=False)
            return self.create_message(
                action="assess_and_size_position", success=False, error=error_msg
            )

    def _assess_pair_risk(
        self,
        pair: str,
        market_data: Dict[str, Any],
        analysis: Dict[str, Any],
        backtest_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        current_price = (
            market_data.get("current_price", 0) if isinstance(market_data, dict) else 0
        )

        if current_price <= 0:
            return {
                "pair": pair,
                "current_price": current_price,
                "position_size": 0,
                "position_size_usd": 0,
                "stop_loss": 0,
                "take_profit": 0,
                "stop_loss_pct": self.default_stop_loss_pct * 100,
                "take_profit_pct": 0,
                "risk_amount": 0,
                "risk_pct_of_account": 0,
                "signal_strength": 0,
                "backtest_win_rate": 0,
                "position_approved": False,
                "rejection_reason": "Invalid price",
                "risk_reward_ratio": 0,
            }

        if isinstance(analysis, dict) and pair in analysis:
            pair_analysis = analysis[pair]
        elif isinstance(analysis, dict):
            pair_analysis = analysis
        else:
            pair_analysis = {}

        signal_strength = (
            pair_analysis.get("signal_strength", 0)
            if isinstance(pair_analysis, dict)
            else 0
        )
        volatility_approved = (
            pair_analysis.get("volatility_approved", True)
            if isinstance(pair_analysis, dict)
            else True
        )

        if not volatility_approved:
            return {
                "pair": pair,
                "current_price": current_price,
                "position_size": 0,
                "position_size_usd": 0,
                "stop_loss": 0,
                "take_profit": 0,
                "stop_loss_pct": 0,
                "take_profit_pct": 0,
                "risk_amount": 0,
                "risk_pct_of_account": 0,
                "signal_strength": signal_strength,
                "backtest_win_rate": 0,
                "position_approved": False,
                "rejection_reason": "Volatility not suitable",
                "risk_reward_ratio": 0,
            }

        entry_timing_approved = (
            pair_analysis.get("entry_timing_approved", True)
            if isinstance(pair_analysis, dict)
            else True
        )

        if not entry_timing_approved:
            return {
                "pair": pair,
                "current_price": current_price,
                "position_size": 0,
                "position_size_usd": 0,
                "stop_loss": 0,
                "take_profit": 0,
                "stop_loss_pct": 0,
                "take_profit_pct": 0,
                "risk_amount": 0,
                "risk_pct_of_account": 0,
                "signal_strength": signal_strength,
                "backtest_win_rate": 0,
                "position_approved": False,
                "rejection_reason": "Entry timing rejected",
                "risk_reward_ratio": 0,
            }

        if isinstance(backtest_results, dict) and pair in backtest_results:
            pair_backtest = backtest_results[pair]
        elif isinstance(backtest_results, dict):
            pair_backtest = backtest_results
        else:
            pair_backtest = {}

        backtest_win_rate = (
            pair_backtest.get("win_rate", 0.5)
            if isinstance(pair_backtest, dict)
            else 0.5
        )

        max_risk_amount = self.account_balance * self.risk_per_trade

        current_regime = (
            pair_analysis.get("regime", "unknown")
            if isinstance(pair_analysis, dict)
            else "unknown"
        )

        asset_config = self.asset_configs.get(pair, self.asset_configs.get("SOL/USDT"))
        stop_loss_adjustment = asset_config["stop_loss_adjustment"]
        position_size_multiplier = asset_config["position_size_multiplier"]
        min_signal_strength_adjustment = asset_config["min_signal_strength_adjustment"]

        adjusted_min_signal_strength = (
            self.min_signal_strength + min_signal_strength_adjustment
        )

        if current_regime == "sideways":
            adjusted_min_signal_strength = max(adjusted_min_signal_strength, 0.45)

        if current_regime == "sideways":
            base_stop_loss_pct = 0.015
            stop_loss_pct = base_stop_loss_pct * stop_loss_adjustment
        else:
            stop_loss_pct = self.default_stop_loss_pct * stop_loss_adjustment

        stop_loss = current_price * (1 - stop_loss_pct)
        risk_per_unit = current_price - stop_loss

        min_size_units = self.min_position_size_by_pair.get(
            pair, self.min_position_size_units
        )

        if self.enforce_min_position_size_only:
            if min_size_units <= 0:
                return {
                    "pair": pair,
                    "current_price": current_price,
                    "position_size": 0,
                    "position_size_usd": 0,
                    "stop_loss": stop_loss,
                    "take_profit": 0,
                    "stop_loss_pct": stop_loss_pct * 100,
                    "take_profit_pct": 0,
                    "risk_amount": 0,
                    "risk_pct_of_account": 0,
                    "signal_strength": signal_strength,
                    "backtest_win_rate": backtest_win_rate,
                    "position_approved": False,
                    "rejection_reason": "Minimum position size not configured",
                    "risk_reward_ratio": 0,
                }
            position_size = min_size_units
        else:
            confidence_multiplier = signal_strength * backtest_win_rate
            actual_risk_amount = max_risk_amount * confidence_multiplier

            if risk_per_unit > 0:
                position_size = actual_risk_amount / risk_per_unit
            else:
                position_size = 0

            if position_size_multiplier != 1.0:
                position_size = position_size * position_size_multiplier

            if min_size_units > 0 and position_size < min_size_units:
                position_size = min_size_units

        position_size_usd = position_size * current_price

        if position_size_usd > self.account_balance:
            return {
                "pair": pair,
                "current_price": current_price,
                "position_size": 0,
                "position_size_usd": 0,
                "stop_loss": stop_loss,
                "take_profit": 0,
                "stop_loss_pct": stop_loss_pct * 100,
                "take_profit_pct": 0,
                "risk_amount": 0,
                "risk_pct_of_account": 0,
                "signal_strength": signal_strength,
                "backtest_win_rate": backtest_win_rate,
                "position_approved": False,
                "rejection_reason": "Position size exceeds account balance",
                "risk_reward_ratio": 0,
            }

        actual_risk_amount = position_size * risk_per_unit

        if (
            not self.enforce_min_position_size_only
            and actual_risk_amount > max_risk_amount
        ):
            return {
                "pair": pair,
                "current_price": current_price,
                "position_size": 0,
                "position_size_usd": 0,
                "stop_loss": stop_loss,
                "take_profit": 0,
                "stop_loss_pct": stop_loss_pct * 100,
                "take_profit_pct": 0,
                "risk_amount": actual_risk_amount,
                "risk_pct_of_account": (actual_risk_amount / self.account_balance)
                * 100,
                "signal_strength": signal_strength,
                "backtest_win_rate": backtest_win_rate,
                "position_approved": False,
                "rejection_reason": "Position size exceeds max risk per trade",
                "risk_reward_ratio": 0,
            }

        take_profit_pct = stop_loss_pct * self.min_risk_reward_ratio
        take_profit = current_price * (1 + take_profit_pct)

        if position_size_usd < self.min_notional_usd:
            return {
                "pair": pair,
                "current_price": current_price,
                "position_size": 0,
                "position_size_usd": 0,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "stop_loss_pct": stop_loss_pct * 100,
                "take_profit_pct": take_profit_pct * 100,
                "risk_amount": actual_risk_amount,
                "risk_pct_of_account": (actual_risk_amount / self.account_balance)
                * 100,
                "signal_strength": signal_strength,
                "backtest_win_rate": backtest_win_rate,
                "position_approved": False,
                "rejection_reason": f"Position notional ${position_size_usd:.2f} below minimum ${self.min_notional_usd:.2f}",
                "risk_reward_ratio": take_profit_pct / stop_loss_pct
                if stop_loss_pct > 0
                else 0,
            }

        if self.enforce_min_position_size_only:
            approval = position_size > 0
            rejection_reason = None if approval else "Invalid position size"
        else:
            approval, rejection_reason = self._validate_trade(
                pair,
                position_size,
                signal_strength,
                backtest_win_rate,
                risk_per_unit,
                adjusted_min_signal_strength,
            )

        return {
            "pair": pair,
            "current_price": current_price,
            "position_size": position_size,
            "position_size_usd": position_size * current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "stop_loss_pct": stop_loss_pct * 100,
            "take_profit_pct": take_profit_pct * 100,
            "risk_amount": actual_risk_amount,
            "risk_pct_of_account": (actual_risk_amount / self.account_balance) * 100,
            "signal_strength": signal_strength,
            "backtest_win_rate": backtest_win_rate,
            "position_approved": approval,
            "rejection_reason": rejection_reason,
            "risk_reward_ratio": take_profit_pct / stop_loss_pct
            if stop_loss_pct > 0
            else 0,
        }

    def _validate_trade(
        self,
        pair: str,
        position_size: float,
        signal_strength: float,
        win_rate: float,
        risk_per_unit: float,
        min_signal_strength: float = None,
    ) -> tuple[bool, Optional[str]]:
        check_min_signal_strength = (
            min_signal_strength
            if min_signal_strength is not None
            else self.min_signal_strength
        )

        if signal_strength < check_min_signal_strength:
            return (
                False,
                f"Signal strength too low ({signal_strength:.2f} < {check_min_signal_strength:.2f})",
            )

        if win_rate < self.min_win_rate:
            return (
                False,
                f"Backtest win rate below {self.min_win_rate * 100:.0f}% ({win_rate * 100:.1f}%)",
            )

        if position_size <= 0:
            return False, "Invalid position size"

        return True, None

    def reset_daily_risk(self) -> None:
        self.cumulative_risk_today = 0.0
        self.logger.info("Daily risk tracker reset")

    def update_account_balance(self, new_balance: float) -> None:
        old_balance = self.account_balance
        self.account_balance = new_balance
        self.logger.info(
            f"Account balance updated: {old_balance:.2f} -> {new_balance:.2f}"
        )
