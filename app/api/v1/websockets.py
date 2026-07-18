from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

import asyncio

import json

import logging

import time

from datetime import datetime, timedelta, timezone

from typing import Dict, Set



from app.core.database import get_redis
from app.core.config import settings
from app.core import metrics
from app.core.auth import is_valid_key

from app.services.data_ingestion.historical import HistoricalDataFetcher

from app.services.ai_engine.predictor import predictor

import pandas as pd



logger = logging.getLogger(__name__)



router = APIRouter()

fetcher = HistoricalDataFetcher()





class ConnectionManager:

    def __init__(self) -> None:

        self.active: Dict[str, Set[WebSocket]] = {}

        self._max_connections = 500



    async def connect(self, ws: WebSocket, channel: str) -> bool:

        # P1 #6: cap concurrent sockets so one client can't exhaust resources.

        if sum(len(v) for v in self.active.values()) >= self._max_connections:

            metrics.inc("ws_rejected")
            await ws.close(code=1013)  # Service Unavailable / try later

            return False

        await ws.accept()

        self.active.setdefault(channel, set()).add(ws)
        metrics.inc("ws_connections")

        logger.info("WS connected: %s (total=%d)", channel, sum(len(v) for v in self.active.values()))

        return True



    def disconnect(self, ws: WebSocket, channel: str) -> None:

        if channel in self.active:

            self.active[channel].discard(ws)



    async def deliver(self, channel: str, message: dict) -> None:

        for ws in list(self.active.get(channel, set())):

            try:

                await ws.send_json(message)

            except Exception:  # noqa: BLE001

                pass





manager = ConnectionManager()





@router.websocket("/ws/chart/{instrument}")

async def chart_ws(ws: WebSocket, instrument: str, timeframe: str = Query("5m")):

    # Standard 2.2: authenticate the WS upgrade when API auth is enabled.
    if settings.API_AUTH_ENABLED:
        key = ws.query_params.get("api_key") or ws.headers.get(settings.API_KEY_HEADER)
        if not is_valid_key(key):
            metrics.inc("ws_rejected")
            await ws.close(code=4401)
            return
    channel = f"chart:{instrument}:{timeframe}"

    if not await manager.connect(ws, channel):

        return



    try:

        end = datetime.now(timezone.utc)

        start = end - timedelta(days=2)

        try:

            candles = await fetcher.get_candles(instrument, timeframe, start, end, 500)

        except Exception as e:  # noqa: BLE001

            logger.warning("Historical load failed for %s: %s", instrument, e)

            candles = []

        await ws.send_json({"type": "historical", "candles": candles})



        # Live ticks are pushed by the shared dispatcher (run_pubsub_dispatcher),

        # so this loop only drives periodic predictions.

        last_prediction_time = 0.0

        prediction_interval = 30



        try:

            while True:

                now = time.time()

                if now - last_prediction_time > prediction_interval:

                    try:

                        pred = await _run_prediction(instrument, timeframe)

                        await manager.deliver(channel, {"type": "prediction", "prediction": pred})

                        last_prediction_time = now

                    except Exception as e:  # noqa: BLE001

                        logger.error(f"Prediction error: {e}")

                await asyncio.sleep(0.1)

        finally:

            manager.disconnect(ws, channel)

    except WebSocketDisconnect:

        manager.disconnect(ws, channel)

    except Exception as e:  # noqa: BLE001

        logger.error(f"WS error: {e}")

        manager.disconnect(ws, channel)





async def _run_prediction(instrument: str, timeframe: str) -> dict:

    end = datetime.now(timezone.utc)

    start = end - timedelta(hours=12)

    candles = await fetcher.get_candles(instrument, timeframe, start, end, 500)

    candles_df = pd.DataFrame(candles)



    r = get_redis()

    ticks_json = await r.lrange(f"tick:history:{instrument}", -200, -1) if r else []

    ticks = [json.loads(t) for t in ticks_json]



    return await predictor.predict(instrument, candles_df, ticks, 0.0)





async def run_pubsub_dispatcher(shutdown_event: asyncio.Event) -> None:

    """Single shared Redis pub/sub reader that fans ticks out to WS clients.



    P1 #6 fix: one pub/sub connection for the whole process instead of one per

    socket (which exhausted the Redis pool at ~20 connections). Subscribes to

    `ticks:*` and delivers each tick to every `chart:{symbol}:*` channel that

    has subscribers. Must run in the web process (it serves the browsers).

    """

    r = get_redis()

    if r is None:

        logger.warning("Redis unavailable; WS tick dispatcher not started")

        return



    pubsub = r.pubsub()

    try:

        await pubsub.psubscribe("ticks:*")

    except Exception as e:  # noqa: BLE001

        logger.error("Failed to subscribe to ticks: %s", e)

        return



    logger.info("WS tick dispatcher started")

    try:

        while not shutdown_event.is_set():

            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

            if not msg or msg.get("type") != "message":

                continue

            channel = msg["channel"]

            symbol = (channel.decode() if isinstance(channel, bytes) else channel).split(":")[-1]

            try:

                tick = json.loads(msg["data"])

            except Exception:  # noqa: BLE001

                continue

            tick_msg = {"type": "tick", "tick": tick}

            prefix = f"chart:{symbol}:"

            for ch in list(manager.active.keys()):

                if ch.startswith(prefix):

                    await manager.deliver(ch, tick_msg)

    finally:

        try:

            await pubsub.punsubscribe("ticks:*")

            await pubsub.aclose()

        except Exception:  # noqa: BLE001

            pass

        logger.info("WS tick dispatcher stopped")
