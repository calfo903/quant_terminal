"""Standalone worker process for the heavy background loops.



Runs the Binance ingest stream + the learning loop OUTSIDE the web process,

so the API stays thin and can be scaled / restarted independently.



Usage:

    python -m app.worker



In production, set RUN_BACKGROUND_TASKS=False on the web process and run this

worker (and as many copies as you need) separately.

"""

import asyncio

import logging



from app.core.database import init_redis, close_connections, get_redis
from app.core.config import settings

from app.services.data_ingestion.binance_stream import BinanceStreamClient
from app.services.data_ingestion.market_source import LiveRatesSource, LiveRatesWsSource

from app.services.ai_engine.model_registry import model_registry

from app.services.mlops.sentiment import sentiment_engine

from app.core.scheduler import learning_loop



logger = logging.getLogger("worker")





async def _supervised(name: str, coro_factory, shutdown_event: asyncio.Event) -> None:

    while not shutdown_event.is_set():

        try:

            await coro_factory()

        except asyncio.CancelledError:

            raise

        except Exception:  # noqa: BLE001

            logger.exception("Background task '%s' crashed; restarting in 2s", name)

            await asyncio.sleep(2)

    logger.info("Background task '%s' stopped", name)





async def run() -> None:

    shutdown_event = asyncio.Event()



    redis = await init_redis()

    await model_registry.initialize()

    await sentiment_engine.initialize()



    binance_client = BinanceStreamClient(redis)

    tasks = [

        asyncio.create_task(

            _supervised("binance-stream", binance_client.start, shutdown_event),

            name="binance-stream",

        ),

        asyncio.create_task(

            _supervised("learning-loop", lambda: learning_loop(shutdown_event), shutdown_event),

            name="learning-loop",

        ),

    ]




    if settings.FOREX_SOURCE and settings.FOREX_SOURCE.lower() != "none":
        fx_symbols = settings.forex_symbols() + settings.commodity_symbols()
        if settings.LIVERATES_API_KEY and fx_symbols:
            fx_cls = LiveRatesWsSource if (settings.FOREX_SOURCE or "").lower() == "live_rates_ws" else LiveRatesSource
            fx_source = fx_cls(
                fx_symbols, settings.LIVERATES_API_KEY, settings.LIVERATES_POLL_INTERVAL
            )
            tasks.append(
                asyncio.create_task(
                    _supervised("forex-stream", fx_source.start, shutdown_event),
                    name="forex-stream",
                )
            )
        else:
            logger.info("Forex live stream disabled (set FOREX_SOURCE + LIVERATES_API_KEY to enable)")

    logger.info("Worker started (binance-stream + learning-loop + forex-stream)")

    try:

        await asyncio.gather(*tasks, return_exceptions=True)

    finally:

        shutdown_event.set()

        await close_connections()

        logger.info("Worker stopped")





if __name__ == "__main__":

    try:

        asyncio.run(run())

    except KeyboardInterrupt:

        logger.info("Interrupted")
