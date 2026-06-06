"""
Lead-Lag Monitor - The Scout Module
====================================
Watches Binance BTC perpetuals for early price movements before they hit KuCoin.

The Secret: Liquidity flows from Perpetuals -> Spot. Binance moves first, KuCoin follows.
The Edge: 2-5 second warning before cascade hits your exchange.

Uses WebSocket (not polling) for real-time updates.
"""

import asyncio
import glob
import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import websockets

logger = logging.getLogger(__name__)

DEFAULT_DEX_BACKTEST_GLOB = "reports/dex_backtest_*.json"
DEFAULT_KUCOIN_LISTINGS_PATH = "data/kucoin_listings.json"
DEFAULT_DEX_TO_CEX_LAG_DAYS = 30


class LeadLagMonitor:
    """
    Cross-Exchange Early Warning System

    Monitors Binance BTC-USDT Perpetual for sudden movements that
    predict incoming cascade on KuCoin spot/margin.

    Signals:
    - DANGER: BTC dropped >0.5% in <30 seconds -> Exit all positions
    - WARNING: Unusual volume spike -> Reduce exposure
    - OPPORTUNITY: Sharp drop followed by absorption -> Prepare to buy
    """

    def __init__(
        self,
        rapid_move_threshold: float = 0.005,
        rapid_move_window: int = 30,
        volume_spike_multiplier: float = 3.0,
    ):
        self.threshold = rapid_move_threshold
        self.window = rapid_move_window
        self.volume_multiplier = volume_spike_multiplier

        self.price_history: deque = deque(maxlen=120)
        self.volume_history: deque = deque(maxlen=120)

        self.current_price: Optional[float] = None
        self.current_signal: str = "NORMAL"
        self.last_warning_time: Optional[datetime] = None

        self.ws = None
        self.running = False

        self.on_danger_callback: Optional[Callable] = None
        self.on_warning_callback: Optional[Callable] = None

    async def start(self) -> None:
        """Start WebSocket connection to Binance"""
        self.running = True
        uri = "wss://fstream.binance.com/ws/btcusdt@aggTrade"

        logger.info("Connecting to Binance WebSocket for Lead-Lag monitoring...")

        while self.running:
            try:
                async with websockets.connect(uri) as websocket:
                    self.ws = websocket
                    logger.info("Connected to Binance BTC-USDT Perpetual stream")

                    async for message in websocket:
                        if not self.running:
                            break

                        data = json.loads(message)
                        await self._process_trade(data)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket disconnected, reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                await asyncio.sleep(5)

    async def _process_trade(self, trade_data: Dict):
        """Process incoming Binance trade"""
        try:
            price = float(trade_data["p"])
            quantity = float(trade_data["q"])
            timestamp = trade_data["T"] / 1000

            self.current_price = price

            self.price_history.append((timestamp, price))
            self.volume_history.append((timestamp, quantity))

            if len(self.price_history) >= 2:
                signal = self._detect_cascade()

                if signal != self.current_signal:
                    self.current_signal = signal
                    await self._trigger_callback(signal)

        except Exception as e:
            logger.error(f"Trade processing error: {e}")

    def _detect_cascade(self) -> str:
        """
        Detect rapid price movements that indicate cascade.

        Returns:
            "DANGER" | "WARNING" | "OPPORTUNITY" | "NORMAL"
        """
        if len(self.price_history) < 10:
            return "NORMAL"

        now = time.time()
        recent_window = [
            (t, p) for t, p in self.price_history if now - t <= self.window
        ]

        if len(recent_window) < 2:
            return "NORMAL"

        oldest_price = recent_window[0][1]
        newest_price = recent_window[-1][1]
        price_change = (newest_price - oldest_price) / oldest_price

        avg_volume = sum(q for _, q in self.volume_history) / len(self.volume_history)
        recent_volume = sum(q for _, q in list(self.volume_history)[-10:]) / 10
        volume_spike = recent_volume > avg_volume * self.volume_multiplier

        if price_change < -self.threshold:
            if volume_spike:
                logger.warning(
                    f"DANGER: BTC dropped {price_change * 100:.2f}% in {self.window}s "
                    f"with volume spike!"
                )
                return "DANGER"
            else:
                logger.warning(f"WARNING: BTC dropped {price_change * 100:.2f}%")
                return "WARNING"

        elif price_change > self.threshold and volume_spike:
            logger.info(
                f"OPPORTUNITY: BTC pumped {price_change * 100:.2f}% with volume"
            )
            return "OPPORTUNITY"

        return "NORMAL"

    async def _trigger_callback(self, signal: str):
        """Trigger registered callbacks"""
        if signal == "DANGER" and self.on_danger_callback:
            try:
                if asyncio.iscoroutinefunction(self.on_danger_callback):
                    await self.on_danger_callback()
                else:
                    self.on_danger_callback()
            except Exception as e:
                logger.error(f"Danger callback failed: {e}")

        elif signal == "WARNING" and self.on_warning_callback:
            try:
                if asyncio.iscoroutinefunction(self.on_warning_callback):
                    await self.on_warning_callback()
                else:
                    self.on_warning_callback()
            except Exception as e:
                logger.error(f"Warning callback failed: {e}")

    def stop(self) -> None:
        """Stop WebSocket monitoring"""
        self.running = False
        logger.info("Lead-Lag monitor stopped")

    def get_status(self) -> Dict:
        """Get current monitoring status"""
        return {
            "connected": self.running,
            "current_price": self.current_price,
            "signal": self.current_signal,
            "data_points": len(self.price_history),
        }

    def start_in_thread(self) -> None:
        """Start WebSocket in background thread"""

        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.start())

        thread = threading.Thread(target=run_async, daemon=True)
        thread.start()
        logger.info("Lead-Lag monitor started in background thread")


class DexToCexLagDetector:
    """
    Offline detector that joins DEX backtest signals to CEX (KuCoin) listings
    to measure the DEX->CEX listing lag and emit lead-lag signals.

    Input sources:
      - reports/dex_backtest_*.json (DEX Intelligence backtest output)
      - data/kucoin_listings.json    (CEX listing reference dataset)

    Output: list of DexCexLagSignal dicts compatible with the orchestrator
    pre-fetch signal shape.

    Signal types:
      - OPPORTUNITY: token was signaled on DEX AND later listed on CEX within
        the lag window (positive lead-lag relationship)
      - WATCH: token was signaled on DEX but is NOT yet listed on CEX
        (no observable listing lag yet)
      - STALE: DEX signal is older than the lag window AND token is not
        listed (signal decay)
    """

    def __init__(
        self,
        lag_window_days: int = DEFAULT_DEX_TO_CEX_LAG_DAYS,
        backtest_glob: str = DEFAULT_DEX_BACKTEST_GLOB,
        listings_path: str = DEFAULT_KUCOIN_LISTINGS_PATH,
        min_composite_score: float = 0.4,
    ):
        self.lag_window_days = lag_window_days
        self.backtest_glob = backtest_glob
        self.listings_path = listings_path
        self.min_composite_score = min_composite_score

        self.dex_signals: List[Dict[str, Any]] = []
        self.cex_listings: Dict[str, Dict[str, Any]] = {}

    def load_kucoin_listings(self, path: Optional[str] = None) -> bool:
        """Load CEX listing reference dataset keyed by upper-case symbol."""
        path = path or self.listings_path
        if not os.path.exists(path):
            logger.warning("KuCoin listings file not found: %s", path)
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load KuCoin listings: %s", exc)
            return False

        listings = data.get("listings", []) if isinstance(data, dict) else []
        self.cex_listings = {
            str(item.get("symbol", "")).upper(): item
            for item in listings
            if item.get("symbol")
        }
        return bool(self.cex_listings)

    def load_dex_backtest(
        self,
        path: Optional[str] = None,
        glob_pattern: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Load DEX backtest signals. If path is None, pick the most recent
        file matching self.backtest_glob."""
        if path:
            files = [path]
        else:
            files = sorted(glob.glob(glob_pattern or self.backtest_glob))
        if not files:
            logger.warning("No DEX backtest files matched: %s", self.backtest_glob)
            self.dex_signals = []
            return []

        latest = files[-1]
        try:
            with open(latest, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load DEX backtest %s: %s", latest, exc)
            self.dex_signals = []
            return []

        per_signal = data.get("signals_with_performance", []) or []
        filtered = [
            s for s in per_signal
            if float(s.get("composite_score", 0) or 0) >= self.min_composite_score
        ]
        self.dex_signals = filtered
        return filtered

    @staticmethod
    def _parse_iso(value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    def _dedupe_first_seen(self) -> Dict[str, Dict[str, Any]]:
        """Group DEX signals by base_token, keep earliest scan_time per token."""
        by_token: Dict[str, Dict[str, Any]] = {}
        for sig in self.dex_signals:
            token = str(sig.get("base_token", "")).upper()
            if not token:
                continue
            scan_time = self._parse_iso(sig.get("scan_time", ""))
            existing = by_token.get(token)
            if existing is None:
                by_token[token] = {**sig, "_scan_dt": scan_time}
            else:
                ex_dt = existing.get("_scan_dt")
                if scan_time and (ex_dt is None or scan_time < ex_dt):
                    by_token[token] = {**sig, "_scan_dt": scan_time}
        return by_token

    def detect(self) -> List[Dict[str, Any]]:
        """Run the join and emit DexCexLagSignal dicts.

        Tokens in cex_listings AND within lag window => OPPORTUNITY.
        Tokens in cex_listings BUT outside lag window => STALE.
        Tokens NOT in cex_listings => WATCH.
        """
        if not self.cex_listings or not self.dex_signals:
            raise RuntimeError(
                "KuCoin listings and DEX backtest must be loaded before calling detect(). "
                "Use run() or call load_kucoin_listings() + load_dex_backtest() first."
            )

        by_token = self._dedupe_first_seen()
        out: List[Dict[str, Any]] = []
        lag_window = timedelta(days=self.lag_window_days)
        now = datetime.now(timezone.utc)

        for token, sig in by_token.items():
            scan_dt = sig.get("_scan_dt")
            listing = self.cex_listings.get(token)
            listing_date_str = listing.get("date") if listing else None
            listing_dt = self._parse_iso(listing_date_str) if listing_date_str else None
            composite = float(sig.get("composite_score", 0) or 0)
            tier = sig.get("confidence_tier", "low")
            chain = listing.get("chain", "solana") if listing else "solana"

            lag_days: Optional[int] = None
            signal_type: str
            confidence: float

            if listing_dt and scan_dt:
                if scan_dt.tzinfo is not None and listing_dt.tzinfo is None:
                    listing_dt = listing_dt.replace(tzinfo=scan_dt.tzinfo)
                elif scan_dt.tzinfo is None and listing_dt.tzinfo is not None:
                    scan_dt = scan_dt.replace(tzinfo=listing_dt.tzinfo)
                delta = listing_dt - scan_dt
                lag_days = delta.days
                if 0 <= lag_days <= self.lag_window_days:
                    signal_type = "OPPORTUNITY"
                    lag_factor = 1.0 - (lag_days / max(self.lag_window_days, 1))
                    confidence = round(min(1.0, composite * 0.6 + lag_factor * 0.4), 3)
                elif lag_days < 0:
                    signal_type = "STALE"
                    confidence = round(composite * 0.3, 3)
                else:
                    signal_type = "STALE"
                    confidence = round(composite * 0.4, 3)
            else:
                signal_type = "WATCH"
                if scan_dt and (now - (scan_dt if scan_dt.tzinfo else scan_dt.replace(tzinfo=timezone.utc))) > lag_window:
                    signal_type = "STALE"
                    confidence = round(composite * 0.5, 3)
                else:
                    confidence = round(composite, 3)

            out.append({
                "base_token": token,
                "chain": chain,
                "dex_pair": sig.get("pair", ""),
                "dex_signal_date": sig.get("scan_time"),
                "cex_listing_date": listing_date_str,
                "lag_days": lag_days,
                "dex_composite_score": composite,
                "dex_confidence_tier": tier,
                "lead_lag_signal": signal_type,
                "confidence": confidence,
                "rationale": (
                    f"DEX {sig.get('signal', 'NEUTRAL')} {lag_days}d before KuCoin listing"
                    if signal_type == "OPPORTUNITY"
                    else f"DEX {sig.get('signal', 'NEUTRAL')} not yet on KuCoin"
                    if signal_type == "WATCH"
                    else f"DEX signal outside {self.lag_window_days}d window"
                ),
            })

        out.sort(key=lambda x: (x["lead_lag_signal"] != "OPPORTUNITY", -x["confidence"]))
        return out

    def run(
        self,
        backtest_path: Optional[str] = None,
        listings_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Convenience wrapper: load both inputs, then detect."""
        if listings_path or not self.cex_listings:
            self.load_kucoin_listings(listings_path)
        if backtest_path or not self.dex_signals:
            self.load_dex_backtest(backtest_path)
        return self.detect()

    def get_status(self) -> Dict[str, Any]:
        return {
            "lag_window_days": self.lag_window_days,
            "min_composite_score": self.min_composite_score,
            "dex_signals_loaded": len(self.dex_signals),
            "cex_listings_loaded": len(self.cex_listings),
            "backtest_glob": self.backtest_glob,
            "listings_path": self.listings_path,
        }
