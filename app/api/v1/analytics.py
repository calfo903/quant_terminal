import json

import logging

from typing import Optional



from fastapi import APIRouter, Query, HTTPException



from app.core.database import get_redis

from app.core.config import settings

from app.services.mlops.sentiment import sentiment_engine



logger = logging.getLogger(__name__)



router = APIRouter()





@router.get("/health-summary")

async def health_summary():

    r = get_redis()

    return {

        "redis": r is not None,

        "sentiment_ready": sentiment_engine.pipeline is not None,

        "min_confidence_threshold": settings.MIN_CONFIDENCE_THRESHOLD,

    }





@router.get("/signals")

async def signals(instrument: str = Query("BTCUSDT")):

    r = get_redis()

    if r is None:

        raise HTTPException(503, "Redis unavailable")

    latest = await r.get(f"tick:latest:{instrument.upper()}")

    if not latest:

        raise HTTPException(404, f"No live data for {instrument}")

    return {"instrument": instrument.upper(), "latest_tick": json.loads(latest)}





@router.get("/risk-metrics")

async def risk_metrics():

    return {

        "max_drawdown_pct": settings.MAX_DRAWDOWN_PCT,

        "target_volatility": settings.TARGET_VOLATILITY,

        "risk_per_trade_pct": settings.RISK_PER_TRADE_PCT,

        "min_confidence_threshold": settings.MIN_CONFIDENCE_THRESHOLD,

        "circuit_breaker_cooldown_hours": settings.CIRCUIT_BREAKER_COOLDOWN_HOURS,

    }
