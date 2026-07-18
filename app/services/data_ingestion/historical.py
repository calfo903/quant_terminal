import json

import logging

from datetime import datetime



from sqlalchemy import text



from app.core.database import TimescaleSession, get_redis





logger = logging.getLogger(__name__)





_TF_SECONDS = {

    "1m": 60,

    "5m": 300,

    "15m": 900,

    "1h": 3600,

    "4h": 14400,

    "1d": 86400,

}



# Mirrors tick_writer.CANDLE_1M_CAP; how many persisted 1m candles we read.

_CANDLE_1M_CAP = 2880





class DataUnavailable(Exception):

    """Raised when the candles store (TimescaleDB) is unreachable.



    Lets callers distinguish 'DB is down' (-> 503) from 'no rows' (-> 404).

    """





class HistoricalDataFetcher:

    """Fetch OHLCV candles from the TimescaleDB `candles` hypertable.



    Falls back to building candles from the Redis tick history (which both the

    Binance and Live-Rates sources populate) when the DB has no rows for a

    symbol. This is what makes forex/commodity charts + indicators + trade

    plans work even though those symbols have no TimescaleDB history.

    """



    CACHE_TTL_SECONDS = 15



    async def get_candles(

        self,

        instrument: str,

        timeframe: str,

        start: datetime,

        end: datetime,

        limit: int = 500,

    ) -> list:

        instrument = instrument.upper()

        cache_key = f"cache:candles:{instrument}:{timeframe}:{limit}"



        # 1) Try the Redis cache first (cheap, offloads the DB).

        r = get_redis()

        if r is not None:

            try:

                cached = await r.get(cache_key)

                if cached:

                    return json.loads(cached)

            except Exception as e:  # noqa: BLE001

                logger.debug("candle cache read failed: %s", e)



        # 2) Hit the database.

        query = text(

            """

            SELECT time, open, high, low, close, volume

            FROM candles

            WHERE instrument = :instrument

              AND timeframe  = :timeframe

              AND time >= :start

              AND time <= :end

            ORDER BY time DESC

            LIMIT :limit

            """

        )

        try:

            async with TimescaleSession() as session:

                result = await session.execute(

                    query,

                    {

                        "instrument": instrument,

                        "timeframe": timeframe,

                        "start": start,

                        "end": end,

                        "limit": int(limit),

                    },

                )

                rows = result.mappings().all()

        except Exception as e:  # noqa: BLE001

            logger.error("Failed to load candles for %s/%s: %s", instrument, timeframe, e)

            raise DataUnavailable(f"candles store unavailable: {e}") from e



        candles = [

            {

                "time": int(r["time"].timestamp()),

                "open": float(r["open"]),

                "high": float(r["high"]),

                "low": float(r["low"]),

                "close": float(r["close"]),

                "volume": float(r["volume"]),

            }

            for r in rows

        ]

        candles.reverse()



        # 3) Fallback: build OHLCV from accumulated Redis tick history. This is

        #    what gives forex / commodities (e.g. XAUUSD) candles when the DB

        #    has none, reusing the exact ticks the live source streams.

        if not candles:

            built = await self._build_from_ticks(instrument, timeframe, start, end, limit)

            if built:

                candles = built



        # 4) Populate the cache (only on a successful read / build).

        if r is not None and candles:

            try:

                await r.set(cache_key, json.dumps(candles), ex=self.CACHE_TTL_SECONDS)

            except Exception as e:  # noqa: BLE001

                logger.debug("candle cache write failed: %s", e)



        return candles



    async def _build_from_ticks(

        self,

        instrument: str,

        timeframe: str,

        start: datetime,

        end: datetime,

        limit: int = 500,

    ) -> list:

        r = get_redis()

        if r is None:

            return []

        # Prefer the persistent 1m candle store (survives restarts, bounded);

        # fall back to raw tick history if it isn't populated yet.

        raw = await r.lrange(f"candle:1m:{instrument}", -_CANDLE_1M_CAP, -1)

        if not raw:

            raw = await r.lrange(f"tick:history:{instrument}", -50000, -1)

        if not raw:

            return []

        tf_sec = _TF_SECONDS.get(timeframe, 60)



        # Normalize into 1m buckets keyed by 1m epoch.

        one_min: Dict[int, Dict[str, float]] = {}

        for x in raw:

            try:

                c = json.loads(x)

            except Exception:  # noqa: BLE001

                continue

            if "time" in c and "close" in c:

                # Already-aggregated 1m candle.

                b = int(c["time"])

                one_min[b] = {

                    "open": float(c.get("open", c["close"])),

                    "high": float(c.get("high", c["close"])),

                    "low": float(c.get("low", c["close"])),

                    "close": float(c["close"]),

                    "n": float(c.get("volume", 1)),

                }

            else:

                # Raw tick.

                price = c.get("price")

                ts = c.get("timestamp")

                if price is None or ts is None:

                    continue

                try:

                    price = float(price)

                    ts = int(ts)

                except (TypeError, ValueError):

                    continue

                b = (ts // 1000 // 60) * 60

                bucket = one_min.get(b)

                if bucket is None:

                    one_min[b] = {"open": price, "high": price, "low": price, "close": price, "n": 1.0}

                else:

                    bucket["high"] = max(bucket["high"], price)

                    bucket["low"] = min(bucket["low"], price)

                    bucket["close"] = price

                    bucket["n"] += 1.0



        if not one_min:

            return []



        # Resample 1m buckets into the requested timeframe.

        times = sorted(one_min.keys())

        step = max(1, tf_sec // 60)

        candles: list = []

        i = 0

        while i < len(times):

            group = times[i : i + step]

            if not group:

                break

            ob = one_min[group[0]]

            cb = one_min[group[-1]]

            high = max(one_min[g]["high"] for g in group)

            low = min(one_min[g]["low"] for g in group)

            vol = sum(one_min[g]["n"] for g in group)

            candles.append(

                {

                    "time": group[0],

                    "open": ob["open"],

                    "high": high,

                    "low": low,

                    "close": cb["close"],

                    "volume": vol,

                }

            )

            i += step



        start_s = int(start.timestamp())

        end_s = int(end.timestamp())

        candles = [c for c in candles if start_s <= c["time"] <= end_s]

        candles.sort(key=lambda c: c["time"])

        return candles[-limit:] if limit else candles
