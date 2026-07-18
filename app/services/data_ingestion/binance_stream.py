import asyncio

import json

import logging

import time

from typing import Callable, Dict, Set

import websockets

from redis.asyncio import Redis
from app.services.data_ingestion.tick_writer import publish_tick

from app.core.config import settings



logger = logging.getLogger(__name__)



class BinanceStreamClient:

    """Production Binance streaming client for Kenya."""

    

    def __init__(self, redis: Redis):

        self.symbols = [s.strip().lower() for s in settings.BINANCE_SYMBOLS.split(",")]

        self.redis = redis

        self._running = False

        self._reconnect_delay = 1

        self._subscribers: Dict[str, Set[Callable]] = {}

    

    async def start(self):

        self._running = True

        while self._running:

            try:

                await self._connect_and_stream()

            except Exception as e:

                logger.error(f"Binance stream error: {e}. Reconnecting in {self._reconnect_delay}s...")

                await asyncio.sleep(self._reconnect_delay)

                self._reconnect_delay = min(self._reconnect_delay * 2, 60)

    

    async def stop(self):

        self._running = False

    

    async def _connect_and_stream(self):

        streams = "/".join([f"{symbol}@trade" for symbol in self.symbols])

        url = f"{settings.BINANCE_WS_URL}/{streams}"

        

        logger.info(f"Connecting to Binance WebSocket: {len(self.symbols)} symbols")

        

        async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:

            self._reconnect_delay = 1

            logger.info("Binance stream connected successfully")

            

            async for message in ws:

                try:

                    data = json.loads(message)

                    await self._handle_message(data)

                except json.JSONDecodeError:

                    continue

                except Exception as e:

                    logger.error(f"Message handling error: {e}")

    

    async def _handle_message(self, data: Dict):

        if "e" not in data or data["e"] != "trade":

            return

        

        symbol = data["s"].upper()

        price = float(data["p"])

        quantity = float(data["q"])

        is_buyer_maker = data["m"]

        timestamp = data["T"]

        

        tick = {

            "instrument": symbol,

            "timestamp": timestamp,

            "price": price,

            "quantity": quantity,

            "is_buy": not is_buyer_maker,

            "received_at": time.time(),

        }

        

        await publish_tick(self.redis, tick)

        

        for cb in self._subscribers.get(symbol, set()):

            try:

                await cb(tick)

            except Exception as e:

                logger.error(f"Subscriber callback error: {e}")

    

    def subscribe(self, symbol: str, callback: Callable):

        self._subscribers.setdefault(symbol, set()).add(callback)
