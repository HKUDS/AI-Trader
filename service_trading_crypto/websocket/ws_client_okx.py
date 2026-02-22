"""
OKX WebSocket client: subscribe to one or more candle (or ticker) channels, push CandleLike (with channel).
Runs in a dedicated thread; reconnects on disconnect.
"""

import asyncio
import json
import logging
import threading
import time
import websockets

from queue import Queue
from typing import List, Optional
from service_trading_crypto.indicators import CandleLike

logger = logging.getLogger(__name__)


class OkxWsClient:
    """
    Async WebSocket client for OKX: one or multiple candle channels.
    Pushes CandleLike (with channel field) to output_queue.
    """

    def __init__(
        self,
        url: str,
        symbol: str,
        channels: List[str],
        output_queue: Queue,
        ping_interval: float = 25.0,
        reconnect_delay: float = 5.0,
    ) -> None:
        self.url = url
        self.symbol = symbol
        self.channels = channels
        self.output_queue = output_queue or Queue()
        self.ping_interval = ping_interval
        self.reconnect_delay = reconnect_delay
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        while not self._stop.is_set():
            try:
                self._loop.run_until_complete(self._connect_and_consume())
            except Exception as e:
                logger.exception("OKX WS loop error: %s", e)
            if not self._stop.is_set():
                time.sleep(self.reconnect_delay)

    async def _connect_and_consume(self) -> None:
        async with websockets.connect(
            self.url,
            ping_interval=self.ping_interval,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            # Support tickers for single-channel mode
            args = []
            for ch in self.channels:
                if ch == "tickers":
                    args.append({"channel": "tickers", "instType": "SPOT", "instId": self.symbol})
                else:
                    args.append({"channel": ch, "instId": self.symbol})
            sub = {"op": "subscribe", "args": args}
            
            print("sub: ", sub)
            await ws.send(json.dumps(sub))
            logger.info("OKX subscribed: %s %s", ", ".join(self.channels), self.symbol)

            while not self._stop.is_set():
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30.0)
                except asyncio.TimeoutError:
                    continue
                data = json.loads(msg)
                if "data" not in data or not isinstance(data["data"], list):
                    continue
                arg = data.get("arg", {})
                channel = arg.get("channel", "")

                for item in data["data"]:
                    candle = None
                    if channel.startswith("candle"):
                        if isinstance(item, list) and len(item) >= 5:
                            try:
                                candle = CandleLike.from_okx_candle(item, channel=channel)
                            except (IndexError, ValueError, TypeError) as e:
                                logger.debug("Skip invalid candle: %s", e)
                    elif channel == "tickers" and isinstance(item, dict) and "last" in item:
                        try:
                            ts = str(item.get("ts", ""))
                            last = float(item["last"])
                            candle = CandleLike(
                                ts=ts, open=last, high=last, low=last,
                                close=last, volume=float(item.get("vol24h", 0) or 0),
                                channel=channel,
                            )
                        except (KeyError, ValueError, TypeError) as e:
                            logger.debug("Skip invalid ticker: %s", e)

                    if candle is not None:
                        self.output_queue.put(candle)
                        logger.info(
                            "%s %s | ts=%s open=%.2f high=%.2f low=%.2f close=%.2f",
                            channel, self.symbol,
                            candle.ts, candle.open, candle.high, candle.low, candle.close,
                        )


    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("OkxWsClient started")


    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._thread = None
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        logger.info("OkxWsClient stopped")
