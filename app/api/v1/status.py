import json

import logging

import time

from datetime import datetime, timezone



from fastapi import APIRouter



from app.core.database import get_redis

from app.core.config import settings



logger = logging.getLogger(__name__)



router = APIRouter()



# A source is considered "streaming" if at least one of its symbols had a tick

# within this many seconds.

STREAM_THRESHOLD_S = 30



Groups = [

    ("binance", "crypto", lambda: [

        s.strip().upper() for s in settings.BINANCE_SYMBOLS.split(",") if s.strip()

    ]),

    ("live_rates", "forex", lambda: settings.forex_symbols() + settings.commodity_symbols()),

]





@router.get("")

async def status():

    """Report which market sources are currently streaming.



    Inferred from Redis tick recency (no extra bookkeeping needed): for each

    source we look at the most recent ``tick:latest`` among its symbols.

    """

    r = get_redis()

    sources = []

    for name, kind, syms_fn in Groups:

        symbols = syms_fn()

        age = None

        if r is not None and symbols:

            try:

                raws = await r.mget([f"tick:latest:{s}" for s in symbols])

                now = time.time()

                ages = []

                for x in raws:

                    if not x:

                        continue

                    try:

                        d = json.loads(x)

                        ra = d.get("received_at")

                        if ra:

                            ages.append(now - float(ra))

                    except Exception:  # noqa: BLE001

                        continue

                if ages:

                    age = round(min(ages), 1)

            except Exception as e:  # noqa: BLE001

                logger.debug("status read failed for %s: %s", name, e)



        if age is None:

            state = "idle"

        elif age < STREAM_THRESHOLD_S:

            state = "streaming"

        else:

            state = "stale"



        sources.append(

            {

                "name": name,

                "kind": kind,

                "status": state,

                "last_tick_age_s": age,

                "symbols": len(symbols),

            }

        )



    return {

        "generated_at": datetime.now(timezone.utc).isoformat(),

        "sources": sources,

    }
