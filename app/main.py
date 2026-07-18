import asyncio

import logging

from contextlib import asynccontextmanager

import time

from fastapi import FastAPI, HTTPException, Depends, Request

from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text

from app.core.config import settings
from app.core.auth import require_api_key
from app.core import metrics
from app.api.v1.metrics import router as metrics_router

from app.core.database import init_redis, close_connections, get_redis, timescale_engine

from app.services.ai_engine.model_registry import model_registry

from app.services.mlops.sentiment import sentiment_engine

from app.services.data_ingestion.binance_stream import BinanceStreamClient
from app.services.data_ingestion.market_source import LiveRatesSource, LiveRatesWsSource

from app.core.scheduler import learning_loop

from app.api.v1 import charts, websockets, image_analysis, analytics, news, chat, status, sessions

from app.api.v1.websockets import run_pubsub_dispatcher



from app.core.logging import configure_logging, get_logger

configure_logging()

logger = get_logger(__name__)



binance_client = None





async def _supervised(name: str, coro_factory, shutdown_event: asyncio.Event) -> None:

    """Run a background coroutine, restarting it on unexpected failure until

    shutdown is requested. Cancellation during shutdown is propagated so the

    task ends cleanly instead of being destroyed mid-flight.

    """

    while not shutdown_event.is_set():

        try:

            await coro_factory()

        except asyncio.CancelledError:

            raise

        except Exception:  # noqa: BLE001

            logger.exception("Background task '%s' crashed; restarting in 2s", name)

            await asyncio.sleep(2)

    logger.info("Background task '%s' stopped", name)





@asynccontextmanager

async def lifespan(app: FastAPI):

    global binance_client

    logger.info("=== Starting Quant AI Terminal ===")



    shutdown_event = asyncio.Event()



    # Initialize services

    redis = await init_redis()

    await model_registry.initialize()

    await sentiment_engine.initialize()



    # Start supervised background tasks.

    # The WS tick dispatcher MUST run in the web process (it fans ticks out to

    # connected browsers). The heavier ingest + learning loops are optional here

    # and should be externalized to `python -m app.worker` in production.

    binance_client = BinanceStreamClient(redis)

    tasks = [

        asyncio.create_task(

            _supervised("ws-pubsub-dispatcher", run_pubsub_dispatcher, shutdown_event),

            name="ws-pubsub-dispatcher",

        ),

    ]

    if settings.RUN_BACKGROUND_TASKS:

        tasks.append(

            asyncio.create_task(

                _supervised("binance-stream", binance_client.start, shutdown_event),

                name="binance-stream",

            )

        )

        tasks.append(

            asyncio.create_task(

                _supervised("learning-loop", lambda: learning_loop(shutdown_event), shutdown_event),

                name="learning-loop",

            )

        )

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
    else:

        logger.info("RUN_BACKGROUND_TASKS=False: start Binance ingest + learning via `python -m app.worker`")



    logger.info("=== All services online ===")

    try:

        yield

    finally:

        logger.info("=== Shutting down ===")

        shutdown_event.set()

        if binance_client:

            await binance_client.stop()



        for task in tasks:

            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)



        await close_connections()

        logger.info("=== Shutdown complete ===")





app = FastAPI(

    title=settings.APP_NAME,

    version="3.2.0",
    dependencies=[Depends(require_api_key)],

    lifespan=lifespan,

)



app.add_middleware(

    CORSMiddleware,

    allow_origins=[settings.FRONTEND_URL],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Record request count, latency, status, and rate-limit denials (5.2)."""
    start = time.time()
    try:
        response = await call_next(request)
    except Exception:
        metrics.record_request(time.time() - start, 500, request.method)
        raise
    if response.status_code == 429:
        metrics.inc("rate_limit_denied")
    metrics.record_request(time.time() - start, response.status_code, request.method)
    return response



app.include_router(charts.router, prefix="/api/v1/charts", tags=["charts"])

app.include_router(websockets.router, prefix="/api/v1", tags=["streaming"])

app.include_router(image_analysis.router, prefix="/api/v1/image", tags=["image"])

app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])

app.include_router(news.router, prefix="/api/v1/news", tags=["news"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])

app.include_router(status.router, prefix="/api/v1/status", tags=["status"])
app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["sessions"])
app.include_router(metrics_router)



@app.get("/healthz")

async def healthz():

    """Liveness probe: the process is alive.

    Intentionally cheap and dependency-free — a failing Redis/DB must NOT cause

    a container restart (that's what readiness is for).

    """

    return {"status": "alive", "app": settings.APP_NAME, "version": app.version}





async def _readiness() -> dict:

    """Readiness probe: can this instance serve traffic right now?

    Pings Redis + DB (with bounded timeouts so the probe can't hang) and

    reports per-dependency status. Models are reported but non-critical.

    """

    components: dict = {}



    # Redis

    r = get_redis()

    if r is None:

        components["redis"] = {"status": "down", "detail": "not initialized"}

    else:

        try:

            await asyncio.wait_for(r.ping(), timeout=3.0)

            components["redis"] = {"status": "ok"}

        except Exception as e:  # noqa: BLE001

            components["redis"] = {"status": "down", "detail": str(e)}



    # Database

    try:

        conn = await asyncio.wait_for(timescale_engine.connect(), timeout=3.0)

        try:

            await conn.execute(text("SELECT 1"))

            components["database"] = {"status": "ok"}

        finally:

            await conn.close()

    except Exception as e:  # noqa: BLE001

        components["database"] = {"status": "down", "detail": str(e)}



    # Models are reported but non-critical for readiness (predictor degrades).

    components["models"] = {

        "tft_loaded": model_registry.tft_model is not None,

        "lgbm_loaded": model_registry.lgbm_model is not None,

        "sentiment_loaded": sentiment_engine.pipeline is not None,

    }



    ready = (

        components.get("database", {}).get("status") == "ok"

        and components.get("redis", {}).get("status") == "ok"

    )

    payload = {"status": "ok" if ready else "degraded", "components": components}

    if not ready:

        # 503 tells the load balancer / orchestrator to stop sending traffic.

        raise HTTPException(status_code=503, detail=payload)

    return payload





@app.get("/readyz")

async def readyz():

    """Readiness probe — see _readiness()."""

    return await _readiness()





@app.get("/health")

async def health():

    """Backward-compatible alias for the readiness probe."""

    return await _readiness()
