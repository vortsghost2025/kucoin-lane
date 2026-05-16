"""
Lead-Lag Monitor - The Scout Module
====================================
Watches Binance BTC perpetuals for early price movements before they hit KuCoin.

The Secret: Liquidity flows from Perpetuals -> Spot. Binance moves first, KuCoin follows.
The Edge: 2-5 second warning before cascade hits your exchange.

Uses WebSocket (not polling) for real-time updates.
"""

import asyncio
import json
import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional

import websockets

logger = logging.getLogger(__name__)


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

    async def start(self):
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

    def stop(self):
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

    def start_in_thread(self):
        """Start WebSocket in background thread"""

        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.start())

        thread = threading.Thread(target=run_async, daemon=True)
        thread.start()
        logger.info("Lead-Lag monitor started in background thread")
