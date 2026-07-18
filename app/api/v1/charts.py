from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, HTTPException, Depends

import pandas as pd
import numpy as np

from app.core.database import get_db, get_redis

from app.services.data_ingestion.historical import HistoricalDataFetcher, DataUnavailable

from app.services.ai_engine.predictor import predictor

from app.services.risk.manager import risk_manager
from app.services.ai_engine.trade_plan import trade_plan_service
from app.services.ai_engine.market_strength import market_strength_service

from app.core.ratelimit import limit_predict

import json

import logging



logger = logging.getLogger(__name__)



router = APIRouter()

fetcher = HistoricalDataFetcher()



@router.get("/{instrument}/candles")

async def get_candles(

    instrument: str,

    timeframe: str = Query("5m", regex="^(1m|5m|15m|1h|4h|1d)$"),

    limit: int = Query(500, ge=10, le=2000),

):

    # Timezone-aware UTC (P2 #12): previously used naive datetime.utcnow().

    end = datetime.now(timezone.utc)

    start = end - timedelta(days=7)

    try:

        candles = await fetcher.get_candles(instrument, timeframe, start, end, limit)

    except DataUnavailable:

        # DB is down - signal dependency failure (distinct from "no rows").

        raise HTTPException(503, "Historical data store unavailable")

    if not candles:

        raise HTTPException(404, f"No data for {instrument}")

    return {"instrument": instrument, "timeframe": timeframe, "candles": candles}



@router.get("/{instrument}/latest")

async def get_latest(instrument: str):

    r = get_redis()

    if r is None:

        raise HTTPException(503, "Redis unavailable")

    tick = await r.get(f"tick:latest:{instrument}")

    if not tick:

        raise HTTPException(404, f"No live data for {instrument}")

    return json.loads(tick)



@router.post("/{instrument}/predict", dependencies=[Depends(limit_predict)])

async def predict(instrument: str):

    try:

        end = datetime.now(timezone.utc)

        start = end - timedelta(hours=12)

        candles_list = await fetcher.get_candles(instrument, "5m", start, end, 500)

        if len(candles_list) < 60:

            raise HTTPException(400, "Insufficient historical data")

        candles_df = pd.DataFrame(candles_list)

        r = get_redis()

        ticks_json = await r.lrange(f"tick:history:{instrument}", -200, -1) if r else []

        ticks = [json.loads(t) for t in ticks_json]

        prediction = await predictor.predict(instrument, candles_df, ticks, 0.0)

        current_price = prediction["features"]["close"]

        atr = prediction["features"]["atr"]

        spread = prediction["features"]["spread"]

        equity = 10000.0

        risk_check = await risk_manager.check_all(

            current_equity=equity,

            signal_confidence=prediction["confidence"],

            atr_pct=atr / current_price if current_price > 0 else 0,

            spread_pct=spread / current_price if current_price > 0 else 0,

        )

        if risk_check["allowed"]:

            position_size = risk_manager.size_position(

                equity=equity,

                atr=atr,

                price=current_price,

                confidence=prediction["confidence"],

            )

            prediction["position_size"] = position_size

        prediction["risk_check"] = risk_check

        return prediction

    except HTTPException:

        raise

    except Exception as e:

        logger.error(f"Prediction failed: {e}", exc_info=True)

        raise HTTPException(500, f"Prediction failed: {str(e)}")


@router.get("/symbols")
async def symbols():
    """Full tradeable-symbol catalog grouped by market (crypto / forex / commodities).

    Powers the chart toolbar dropdown & symbol search and guarantees XAUUSD etc.
    appear without hard-coding them in the frontend.
    """
    return settings.symbol_catalog()


@router.get("/{instrument}/indicators")
async def indicators(
    instrument: str,
    timeframe: str = Query("5m", regex="^(1m|5m|15m|1h|4h|1d)$"),
    limit: int = Query(500, ge=10, le=2000),
):
    """Compute overlay indicators (SMA/EMA/RSI) for the charts tool.

    Returns time-aligned arrays so the frontend can draw MA/EMA lines and an
    RSI sub-pane. Degrades gracefully: empty arrays if data is unavailable.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    try:
        candles = await fetcher.get_candles(instrument, timeframe, start, end, limit)
    except DataUnavailable:
        raise HTTPException(503, "Historical data store unavailable")
    if not candles:
        return {
            "instrument": instrument,
            "timeframe": timeframe,
            "times": [],
            "sma20": [],
            "sma50": [],
            "ema20": [],
            "rsi14": [],
        }

    df = pd.DataFrame(candles)
    close = pd.to_numeric(df["close"], errors="coerce").astype(float)
    times = [int(c["time"]) for c in candles]

    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    rsi14 = pd.Series(_rsi_series(close, 14))

    def pack(series):
        return [
            None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(float(v), 4)
            for v in series.tolist()
        ]

    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "times": times,
        "sma20": pack(sma20),
        "sma50": pack(sma50),
        "ema20": pack(ema20),
        "rsi14": pack(rsi14),
    }


def _rsi_series(close: "pd.Series", period: int = 14):
    if len(close) <= period:
        return [50.0] * len(close)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0).tolist()


@router.post("/{instrument}/plan")
async def plan(
    instrument: str,
    timeframe: str = Query("5m", regex="^(1m|5m|15m|1h|4h|1d)$"),
    _: None = Depends(limit_predict),
):
    """Compute a full trade plan: entry, stop-loss, take-profit, a predictive
    forecast line, and detected pattern formations.

    Uses recent candles + the (optional) ML predictor. Degrades to technical
    heuristics when the predictor/DB is unavailable. Returns 503 if there is no
    candle history to plan from.
    """
    try:
        return await trade_plan_service.build(instrument, timeframe)
    except DataUnavailable:
        raise HTTPException(503, "Historical data store unavailable")


@router.get("/{instrument}/strength")
async def strength(
    instrument: str,
    timeframe: str = Query("5m", regex="^(1m|5m|15m|1h|4h|1d)$"),
    limit: int = Query(500, ge=10, le=2000),
):
    """Market-strength indicators: ADX, RSI, MACD, Bollinger %B, ATR%, volume
    ratio, plus a composite 0-100 strength score and bias. Returns time-aligned
    `adx_series` / `strength_series` for charting. 503 if no candle history.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    try:
        return await market_strength_service.compute(instrument, timeframe, limit)
    except DataUnavailable:
        raise HTTPException(503, "Historical data store unavailable")
