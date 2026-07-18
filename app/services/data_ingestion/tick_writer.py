import json

import logging

from typing import Dict, Any, Optional, Set



from redis.asyncio import Redis



from app.core.config import settings



logger = logging.getLogger(__name__)



# Cap of persisted 1m candles per symbol (~2 days at 1m). Keeps the forex/

# commodity history bounded while giving the trade-plan/indicators enough

# depth to work within minutes of streaming (and surviving restarts).

CANDLE_1M_CAP = 2880



_crypto_set_cache: Optional[Set[str]] = None





def _crypto_set() -> Set[str]:

    global _crypto_set_cache

    if _crypto_set_cache is None:

        _crypto_set_cache = {

            s.strip().upper() for s in settings.BINANCE_SYMBOLS.split(",") if s.strip()

        }

    return _crypto_set_cache





async def publish_tick(redis: Optional[Redis], tick: Dict[str, Any]) -> None:

    """Write a normalized market tick to Redis the same way for every source.



    Mirrors exactly what ``BinanceStreamClient`` did: latest price, a bounded

    history list, and a ``ticks:{symbol}`` pub/sub message that the WS

    dispatcher fans out to browser charts. Centralizing this lets crypto

    (Binance) and forex/commodities (Live-Rates) share one pipeline.

    """

    if redis is None:

        return

    symbol = tick.get("instrument")

    if not symbol:

        return

    try:

        pipe = redis.pipeline()

        pipe.set(f"tick:latest:{symbol}", json.dumps(tick))

        pipe.rpush(f"tick:history:{symbol}", json.dumps(tick))

        pipe.ltrim(f"tick:history:{symbol}", -50000, -1)

        pipe.publish(f"ticks:{symbol}", json.dumps(tick))

        await pipe.execute()

    except Exception as e:  # noqa: BLE001

        logger.error("publish_tick failed for %s: %s", symbol, e)



    # Persist an aggregated 1m candle for non-crypto symbols (forex/commodities)

    # so historical candles exist even when TimescaleDB has no rows, and survive

    # restarts. Crypto keeps using the DB (high-frequency, no need to aggregate).

    if symbol not in _crypto_set():

        try:

            await _aggregate_1m(redis, symbol, tick)

        except Exception as e:  # noqa: BLE001

            logger.debug("1m aggregate failed for %s: %s", symbol, e)





async def _aggregate_1m(redis: Redis, symbol: str, tick: Dict[str, Any]) -> None:

    price = tick.get("price")

    ts = tick.get("timestamp")

    try:

        price = float(price)

        ts = int(ts)

    except (TypeError, ValueError, KeyError):

        return

    if price <= 0:

        return

    bucket = (ts // 1000 // 60) * 60  # 1m epoch (seconds)

    key = f"candle:1m:{symbol}"

    try:

        last = await redis.lindex(key, -1)

        if last:

            c = json.loads(last)

            if c.get("time") == bucket:

                c["high"] = max(c["high"], price)

                c["low"] = min(c["low"], price)

                c["close"] = price

                c["volume"] = c.get("volume", 0) + 1

                await redis.lset(key, -1, json.dumps(c))

                return

        new_c = {

            "time": bucket,

            "open": price,

            "high": price,

            "low": price,

            "close": price,

            "volume": 1,

        }

        await redis.rpush(key, json.dumps(new_c))

        await redis.ltrim(key, -CANDLE_1M_CAP, -1)

    except Exception as e:  # noqa: BLE001

        logger.debug("1m aggregate redis error for %s: %s", symbol, e)
