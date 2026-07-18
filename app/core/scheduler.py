import asyncio

import logging

import time

from typing import Any, Dict, Optional



from app.core.database import get_redis, TimescaleSession

from sqlalchemy import text



logger = logging.getLogger(__name__)



LEARNING_INTERVAL_SECONDS = 300  # 5 minutes

STATS_KEY = "learning:last_run"





async def learning_loop(shutdown_event: Optional[asyncio.Event] = None) -> None:

    """Background coroutine started (and supervised) by the FastAPI lifespan.



    Runs an incremental learning iteration on a fixed interval. The loop exits

    promptly when `shutdown_event` is set, instead of blocking for a full

    interval on shutdown.

    """

    logger.info("Learning loop started (interval=%ss)", LEARNING_INTERVAL_SECONDS)

    while True:

        if shutdown_event is not None and shutdown_event.is_set():

            logger.info("Learning loop stopping")

            return

        try:

            await _iteration()

        except Exception as e:  # noqa: BLE001 - keep the loop alive

            logger.error(f"Learning loop iteration failed: {e}", exc_info=True)



        # Wait for the interval, but wake immediately if shutdown is requested.

        if shutdown_event is not None:

            try:

                await asyncio.wait_for(shutdown_event.wait(), timeout=LEARNING_INTERVAL_SECONDS)

                logger.info("Learning loop stopping")

                return

            except asyncio.TimeoutError:

                pass

        else:

            await asyncio.sleep(LEARNING_INTERVAL_SECONDS)





async def _iteration() -> Dict[str, Any]:

    """One learning step.



    Example work: refresh a feature-store / model stats key in Redis and run a

    lightweight aggregation over recent market data. Replace the body with your

    real retraining / online-learning logic.

    """

    r = get_redis()

    now = int(time.time())

    summary: Dict[str, Any] = {"last_run": now}



    if r is not None:

        await r.set(STATS_KEY, str(now))



    try:

        async with TimescaleSession() as session:

            # Example aggregation: count ticks ingested in the last hour.

            result = await session.execute(

                text(

                    """

                    SELECT count(*) AS n

                    FROM ticks

                    WHERE received_at >= now() - interval '1 hour'

                    """

                )

            )

            row = result.first()

            summary["ticks_last_hour"] = int(row.n) if row else 0

    except Exception as e:  # noqa: BLE001

        logger.warning(f"Aggregation step skipped: {e}")

        summary["ticks_last_hour"] = None



    logger.info("Learning iteration complete: %s", summary)

    return summary
