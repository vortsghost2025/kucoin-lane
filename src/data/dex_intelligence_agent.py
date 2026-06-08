"""DEX Intelligence Agent — wraps DexScanner as a BaseAgent for orchestrator integration."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from ..base_agent import BaseAgent
from .dex_intelligence.scanner import DexScanner


logger = logging.getLogger(__name__)


class DexIntelligenceAgent(BaseAgent):
    """
    DEX intelligence agent that scans DEX markets for early-token signals.
    
    Runs DexScanner and emits structured signals for the orchestrator to consume.
    Integrates as a pre-fetch intelligence phase before market analysis.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("DexIntelligenceAgent", config)
        
        chains = config.get("chains", ["solana"]) if config else ["solana"]
        rpc_url = config.get("rpc_url") if config else None
        if not rpc_url:
            rpc_url = os.getenv("DEX_PUMPFUN_RPC_URL")
        
        self.scanner = DexScanner(chains=chains, rpc_url=rpc_url)
        self._latest_signals: Dict[str, Any] = {}
        self._scan_interval = config.get("scan_interval_seconds", 300) if config else 300
        self._min_composite_score = config.get("min_composite_score", 0.3) if config else 0.3

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Run DEX scan and return actionable signals."""
        self.log_execution_start("dex_scan")
        
        chain = input_data.get("chain", "solana")
        min_score = input_data.get("min_composite_score", self._min_composite_score)
        
        try:
            scan_result = self.scanner.full_scan(chain=chain)
            
            trending = scan_result.get("top_trending", [])
            new_pools = scan_result.get("top_new_pools", [])
            pumpfun = scan_result.get("pumpfun_graduation_candidates", [])
            
            all_signals = trending + new_pools
            actionable = [s for s in all_signals if s.get("composite_score", 0) >= min_score]
            
            buy_signals = [s for s in actionable if s.get("signal") in ("STRONG_BUY", "BUY")]
            
            self._latest_signals = {
                "dex_signals": buy_signals,
                "scan_summary": scan_result.get("summary"),
                "scan_time": scan_result.get("scan_time"),
                "chain": chain,
            }
            
            self.log_execution_end("dex_scan", success=True)
            
            return self.create_message(
                action="dex_intelligence",
                success=True,
                data={
                    "dex_signals": buy_signals,
                    "scan_summary": scan_result.get("summary"),
                    "scan_time": scan_result.get("scan_time"),
                    "chain": chain,
                    "total_scanned": len(all_signals),
                    "actionable_count": len(buy_signals),
                },
            )
            
        except Exception as e:
            self.log_execution_end("dex_scan", success=False)
            self.set_status(self.status.ERROR, str(e))
            return self.create_message(
                action="dex_intelligence",
                success=False,
                error=f"DEX scan failed: {e}",
                data={"dex_signals": [], "scan_summary": str(e)},
            )

    def get_latest_signals(self) -> Dict[str, Any]:
        """Return the most recent DEX signals for orchestrator consumption."""
        return self._latest_signals

    def get_status_report(self) -> Dict[str, Any]:
        report = super().get_status_report()
        report["latest_scan_time"] = self._latest_signals.get("scan_time")
        report["latest_signal_count"] = len(self._latest_signals.get("dex_signals", []))
        return report