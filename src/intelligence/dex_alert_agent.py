"""
Dex Alert Agent - DEX Signal Alert Pipeline
=============================================
Consumes creator_alerts and dex_signals, scores them, classifies into
STRONG_BUY_ALERT / BUY_ALERT / WATCH_ALERT tiers, and dispatches alerts
to the lane outbox and event log.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..base_agent import BaseAgent, AgentStatus


class DexAlertAgent(BaseAgent):
    """
    DEX Signal Alert Agent

    Responsibilities:
    1. Score creator alerts and DEX signals through a boost/penalty pipeline
    2. Classify alerts into STRONG_BUY, BUY, or WATCH tiers
    3. Deduplicate DEX signals already covered by creator alerts (by mint)
    4. Write alerts to outbox for downstream lane consumption
    5. Log alerts and events to file for audit trail
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("DexAlertAgent", config)
        config = config or {}
        self.outbox_dir = config.get("outbox_dir", "S:/Archivist-Agent/lanes/kucoin/outbox/")
        self.min_alert_score = config.get("min_alert_score", 0.5)
        self.logs_dir = config.get("logs_dir", "./logs")

        self.alerts: List[Dict[str, Any]] = []
        self._latest_alerts: List[Dict[str, Any]] = []
        self._strong_buy_count = 0
        self._buy_count = 0
        self._watch_count = 0

        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.outbox_dir, exist_ok=True)

        self._setup_file_logging()

        self._log_path = os.path.join(self.logs_dir, "dex_alerts.log")
        self._events_path = os.path.join(self.logs_dir, "dex_alert_events.jsonl")

    def _setup_file_logging(self) -> None:
        log_path = os.path.join(self.logs_dir, "dex_alerts.log")
        file_handler = logging.FileHandler(log_path)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        self.log_execution_start("dex_alert_pipeline")

        try:
            creator_alerts = input_data.get("creator_alerts", [])
            dex_signals = input_data.get("dex_signals", [])
            alpha_creators = input_data.get("alpha_creators", [])
            scan_summary = input_data.get("scan_summary", {})

            alpha_ids = set()
            if isinstance(alpha_creators, list):
                for ac in alpha_creators:
                    cid = ac.get("creator_id") if isinstance(ac, dict) else str(ac)
                    if cid:
                        alpha_ids.add(cid)

            seen_mints: set = set()
            scored: List[Dict[str, Any]] = []

            for alert in creator_alerts:
                score = self._score_creator_alert(alert, alpha_ids)
                mint = alert.get("mint", alert.get("address", ""))
                if mint:
                    seen_mints.add(mint)
                scored.append(self._build_alert_record(alert, score, "creator_alert"))

            for signal in dex_signals:
                mint = signal.get("mint", signal.get("address", ""))
                if mint in seen_mints:
                    continue
                score = self._score_dex_signal(signal)
                scored.append(self._build_alert_record(signal, score, "dex_signal"))

            classified = []
            strong_buy = 0
            buy = 0
            watch = 0

            for rec in scored:
                score = rec["score"]
                if score >= 0.8:
                    rec["classification"] = "STRONG_BUY_ALERT"
                    strong_buy += 1
                elif score >= 0.6:
                    rec["classification"] = "BUY_ALERT"
                    buy += 1
                elif score >= 0.4:
                    rec["classification"] = "WATCH_ALERT"
                    watch += 1
                else:
                    continue

                if score < self.min_alert_score:
                    continue

                rec = self._finalize_alert(rec)
                classified.append(rec)
                self.alerts.append(rec)
                self._log_classified_alert(rec)
                self._write_event(rec)
                self._write_outbox(rec)

            self._latest_alerts = classified
            self._strong_buy_count += strong_buy
            self._buy_count += buy
            self._watch_count += watch

            self.log_execution_end("dex_alert_pipeline", success=True)

            return {
                "agent": self.agent_name,
                "action": "dex_alert_pipeline",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": True,
                "data": {
                    "alerts_generated": len(classified),
                    "strong_buy_count": strong_buy,
                    "buy_count": buy,
                    "watch_count": watch,
                    "alerts": classified,
                    "outbox_dir": self.outbox_dir,
                },
            }

        except Exception as e:
            error_msg = f"DexAlertAgent error: {str(e)}"
            self.set_status(AgentStatus.ERROR, error_msg)
            self.log_execution_end("dex_alert_pipeline", success=False)
            return self.create_message(
                action="dex_alert_pipeline", success=False, error=error_msg
            )

    def _score_creator_alert(self, alert: Dict[str, Any], alpha_ids: set) -> float:
        score = alert.get("composite_score", alert.get("score", 0.5))

        creator_id = alert.get("creator_id", alert.get("deployer", ""))
        if creator_id in alpha_ids:
            score += 0.15

        reputation = alert.get("reputation_score", 0.0)
        if reputation > 0.7:
            score += 0.10
        elif reputation > 0.5:
            score += 0.05
        elif reputation < 0.2:
            score -= 0.10

        safety = alert.get("safety_summary", {})
        if isinstance(safety, dict):
            if safety.get("avoid"):
                score -= 0.30
            risk_tier = safety.get("latest_risk_tier", "")
            if "HIGH_RISK" in risk_tier:
                score -= 0.15
            elif "LOW_RISK" in risk_tier:
                score += 0.05

        social = alert.get("social_summary", {})
        if isinstance(social, dict):
            best_composite = social.get("best_composite", 0.0)
            if best_composite > 0.6:
                score += 0.05

        signal_type = alert.get("signal", alert.get("alert_type", ""))
        if signal_type == "ALPHA_CREATOR":
            score += 0.20
        elif signal_type == "REPEAT_CREATOR":
            score += 0.10
        elif signal_type == "NEW_CREATOR":
            score -= 0.05

        return max(0.0, min(1.0, score))

    def _score_dex_signal(self, signal: Dict[str, Any]) -> float:
        score = signal.get("composite_score", signal.get("score", 0.3))

        volume = signal.get("volume_usd", signal.get("volume", 0))
        liquidity = signal.get("liquidity_usd", signal.get("liquidity", 0))
        txns = signal.get("txns", {})

        if volume and isinstance(volume, (int, float)) and volume > 10000:
            score += 0.05
        if liquidity and isinstance(liquidity, (int, float)) and liquidity > 5000:
            score += 0.05

        if isinstance(txns, dict):
            buys = txns.get("buys", 0)
            sells = txns.get("sells", 0)
            total = buys + sells
            if total > 0:
                buy_ratio = buys / total
                if buy_ratio > 0.7:
                    score += 0.05
                elif buy_ratio < 0.3:
                    score -= 0.10

        price_change = signal.get("price_change", signal.get("price_change_percent", 0))
        if isinstance(price_change, (int, float)):
            if price_change > 50:
                score += 0.05
            elif price_change < -30:
                score -= 0.10

        dex = signal.get("dex_id", signal.get("dex", "")).lower()
        if "pump" in dex:
            score -= 0.05

        return max(0.0, min(1.0, score))

    def _build_alert_record(self, source: Dict[str, Any], score: float, signal_type: str) -> Dict[str, Any]:
        creator_id = source.get("creator_id", source.get("deployer", "unknown"))
        creator_name = source.get("display_name", creator_id[:8] + "..." if len(creator_id) > 8 else creator_id)
        token = source.get("pair", source.get("token", source.get("ticker", "")))
        if "/" in token:
            token = token.split("/")[0]
        mint = source.get("mint", source.get("address", ""))
        social_links = source.get("social_links", {})
        safety = source.get("safety_summary", {})
        if not isinstance(safety, dict):
            safety = {}

        return {
            "lane": "kucoin",
            "cycle": self.execution_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": "live",
            "status": "active",
            "phase": "alert",
            "signal_type": signal_type,
            "creator": creator_name,
            "creator_id": creator_id,
            "token": token,
            "mint": mint,
            "score": round(score, 4),
            "classification": "",
            "social_links": social_links,
            "safety": {
                "risk_tier": safety.get("latest_risk_tier", "UNKNOWN"),
                "risk_score": safety.get("latest_risk_score", 0.5),
                "tradeable": safety.get("tradeable", False),
                "avoid": safety.get("avoid", False),
            },
            "source": source.get("source", signal_type),
            "final": False,
        }

    def _finalize_alert(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        classification = rec["classification"]
        if classification == "STRONG_BUY_ALERT":
            rec["status"] = "strong_buy"
            rec["final"] = True
        elif classification == "BUY_ALERT":
            rec["status"] = "buy"
            rec["final"] = False
        else:
            rec["status"] = "watch"
            rec["final"] = False
        return rec

    def _log_classified_alert(self, alert: Dict[str, Any]) -> None:
        classification = alert.get("classification", "")
        token = alert.get("token", "?")
        score = alert.get("score", 0)
        creator = alert.get("creator", "?")
        msg = f"{classification} | {token} | score={score} | creator={creator}"

        if classification == "STRONG_BUY_ALERT":
            self.logger.critical(msg)
        elif classification == "BUY_ALERT":
            self.logger.warning(msg)
        else:
            self.logger.info(msg)

    def _write_event(self, alert: Dict[str, Any]) -> None:
        try:
            with open(self._events_path, "a") as f:
                f.write(json.dumps(alert, default=str) + "\n")
        except IOError as e:
            self.logger.error(f"Failed to write event: {e}")

    def _write_outbox(self, alert: Dict[str, Any]) -> None:
        ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        filename = f"dex_alert_{ts_ms}.json"
        filepath = os.path.join(self.outbox_dir, filename)
        try:
            with open(filepath, "w") as f:
                json.dump(alert, f, indent=2, default=str)
        except IOError as e:
            self.logger.error(f"Failed to write outbox file {filepath}: {e}")

    def get_alerts(self, classification: Optional[str] = None) -> List[Dict[str, Any]]:
        if classification:
            return [a for a in self.alerts if a.get("classification") == classification]
        return self.alerts.copy()

    def get_latest_alerts(self) -> List[Dict[str, Any]]:
        return self._latest_alerts.copy()

    def clear_alerts(self) -> None:
        self.alerts.clear()
        self._latest_alerts.clear()
        self._strong_buy_count = 0
        self._buy_count = 0
        self._watch_count = 0
        self.logger.info("Alerts cleared")

    def get_status_report(self) -> Dict[str, Any]:
        report = super().get_status_report()
        report.update({
            "total_alerts": len(self.alerts),
            "strong_buy_count": self._strong_buy_count,
            "buy_count": self._buy_count,
            "watch_count": self._watch_count,
            "outbox_dir": self.outbox_dir,
            "min_alert_score": self.min_alert_score,
        })
        return report
