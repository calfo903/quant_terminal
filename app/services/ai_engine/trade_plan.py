import logging

from datetime import datetime, timezone

from typing import Any, Dict, List, Optional



import numpy as np

import pandas as pd



from app.core.config import settings

from app.services.ai_engine.predictor import predictor

from app.services.data_ingestion.historical import HistoricalDataFetcher, DataUnavailable



logger = logging.getLogger(__name__)



# Seconds per timeframe bucket.

_TF_SECONDS = {

    "1m": 60,

    "5m": 300,

    "15m": 900,

    "1h": 3600,

    "4h": 14400,

    "1d": 86400,

}





class TradePlanService:

    """Builds a full trade plan (entry / stop / target / forecast / patterns) for

    a symbol from recent candles + the (optional) ML predictor.



    Everything degrades gracefully: if the predictor or DB is unavailable it falls

    back to simple technical heuristics so the chart can still draw a plan.

    """



    def __init__(self) -> None:

        self.fetcher = HistoricalDataFetcher()

        self._atr_mult = 1.5       # stop distance = ATR * mult

        self._rr = 2.0             # reward:risk for take-profit

        self._forecast_bars = 20   # how many future points to project



    async def build(

        self,

        instrument: str,

        timeframe: str = "5m",

        lookback_days: int = 7,

    ) -> Dict[str, Any]:

        end = datetime.now(timezone.utc)

        start = end - pd.Timedelta(days=lookback_days)

        try:

            candles = await self.fetcher.get_candles(instrument, timeframe, start, end, 500)

        except DataUnavailable:

            raise

        if not candles or len(candles) < 20:

            # Not enough data for a reliable plan.

            return self._empty(instrument, timeframe, "insufficient history")



        df = pd.DataFrame(candles)

        close = pd.to_numeric(df["close"], errors="coerce").astype(float)

        high = pd.to_numeric(df["high"], errors="coerce").astype(float)

        low = pd.to_numeric(df["low"], errors="coerce").astype(float)



        last_time = int(candles[-1]["time"])

        last_close = float(close.iloc[-1])

        atr = self._atr(high, low, close, 14)

        if atr <= 0:

            atr = float(close.std()) or last_close * 0.005 or 1.0



        # Direction: prefer the predictor, else a trend heuristic.

        direction, signal, confidence = await self._direction(close, instrument, candles)



        risk = atr * self._atr_mult

        if direction == "long":

            entry = last_close

            stop = entry - risk

            target = entry + risk * self._rr

        elif direction == "short":

            entry = last_close

            stop = entry + risk

            target = entry - risk * self._rr

        else:

            entry = last_close

            stop = entry - risk

            target = entry + risk * self._rr



        rr = abs(target - entry) / abs(entry - stop) if abs(entry - stop) > 1e-9 else 0.0



        # Forecast: simple, volatility-aware linear projection from recent slope.

        forecast = self._forecast(close, last_time, timeframe, direction, atr)



        # Patterns: trend + support/resistance + simple double tops/bottoms.

        patterns, support, resistance = self._patterns(high, low, close)



        return {

            "instrument": instrument.upper(),

            "timeframe": timeframe,

            "direction": direction,

            "signal": signal,

            "confidence": round(float(confidence), 4),

            "current_price": round(last_close, 6),

            "entry": round(float(entry), 6),

            "stop_loss": round(float(stop), 6),

            "take_profit": round(float(target), 6),

            "risk_reward": round(float(rr), 2),

            "forecast": forecast,

            "patterns": patterns,

            "support": round(float(support), 6) if support is not None else None,

            "resistance": round(float(resistance), 6) if resistance is not None else None,

            "atr": round(float(atr), 6),

            "generated_at": datetime.now(timezone.utc).isoformat(),

        }



    async def _direction(self, close: pd.Series, instrument: str, candles: List[Dict]) -> (str, str, float):

        # Try the ML predictor first (graceful if models/data missing).

        try:

            candles_df = pd.DataFrame(candles)

            pred = await predictor.predict(instrument, candles_df, [], 0.0)

            sig = (pred.get("signal") or "HOLD").upper()

            conf = float(pred.get("confidence", 0.5))

            if sig == "BUY":

                return "long", "BUY", conf

            if sig == "SELL":

                return "short", "SELL", conf

        except Exception as e:  # noqa: BLE001

            logger.debug("predictor unavailable for direction: %s", e)



        # Heuristic fallback: close vs SMA20 + momentum.

        if len(close) < 20:

            return "neutral", "HOLD", 0.5

        sma20 = float(close.tail(20).mean())

        mom = float(close.iloc[-1] - close.iloc[-5])

        if close.iloc[-1] > sma20 and mom > 0:

            return "long", "BUY", 0.55

        if close.iloc[-1] < sma20 and mom < 0:

            return "short", "SELL", 0.55

        return "neutral", "HOLD", 0.5



    def _forecast(

        self, close: pd.Series, last_time: int, timeframe: str, direction: str, atr: float

    ) -> List[Dict[str, Any]]:

        step = _TF_SECONDS.get(timeframe, 300)

        n = min(30, len(close))

        recent = close.tail(n).to_numpy()

        # Slope per bar from a linear fit on the recent window.

        x = np.arange(n)

        try:

            slope = float(np.polyfit(x, recent, 1)[0])

        except Exception:  # noqa: BLE001

            slope = 0.0

        # Damp the slope so the projection doesn't run away.

        damped = slope * 0.5

        base = float(close.iloc[-1])

        out: List[Dict[str, Any]] = [

            {"time": last_time, "value": round(base, 6)}  # anchor to last close

        ]

        for i in range(1, self._forecast_bars + 1):

            val = base + damped * i

            out.append({"time": last_time + i * step, "value": round(float(val), 6)})

        return out



    def _patterns(self, high: pd.Series, low: pd.Series, close: pd.Series):

        patterns: List[str] = []

        window = close.tail(40)

        sma20 = float(close.tail(20).mean()) if len(close) >= 20 else float(close.mean())

        # Trend via higher-highs / higher-lows.

        hh = bool(close.iloc[-1] > close.iloc[-10] > close.iloc[-20])

        ll = bool(close.iloc[-1] < close.iloc[-10] < close.iloc[-20])

        if hh and close.iloc[-1] > sma20:

            patterns.append("Uptrend (HH/HL)")

        elif ll and close.iloc[-1] < sma20:

            patterns.append("Downtrend (LH/LL)")

        else:

            patterns.append("Range / consolidation")



        # Support / resistance from recent swing extremes.

        support = float(low.tail(40).min())

        resistance = float(high.tail(40).max())

        patterns.append(f"Support ~{support:.4f}")

        patterns.append(f"Resistance ~{resistance:.4f}")



        # Simple double-top / double-bottom on the last 40 bars.

        doubles = self._double_pivots(high, low)

        patterns.extend(doubles)

        return patterns, support, resistance



    @staticmethod

    def _double_pivots(high: pd.Series, low: pd.Series) -> List[str]:

        out: List[str] = []

        h = high.tail(40).to_numpy()

        l = low.tail(40).to_numpy()

        # Two comparable peaks.

        hi_idx = np.argsort(h)[-2:]

        if len(hi_idx) == 2:

            p1, p2 = sorted(hi_idx)

            if abs(h[p1] - h[p2]) / max(h[p1], 1e-9) < 0.01 and p2 - p1 > 3:

                out.append("Possible Double Top")

        lo_idx = np.argsort(l)[:2]

        if len(lo_idx) == 2:

            p1, p2 = sorted(lo_idx)

            if abs(l[p1] - l[p2]) / max(l[p1], 1e-9) < 0.01 and p2 - p1 > 3:

                out.append("Possible Double Bottom")

        return out



    @staticmethod

    def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:

        if len(high) < 2:

            return 0.0

        prev_close = close.shift(1)

        tr = pd.concat(

            [

                (high - low),

                (high - prev_close).abs(),

                (low - prev_close).abs(),

            ],

            axis=1,

        ).max(axis=1)

        return float(tr.tail(period).mean())



    @staticmethod

    def _empty(instrument: str, timeframe: str, reason: str) -> Dict[str, Any]:

        return {

            "instrument": instrument.upper(),

            "timeframe": timeframe,

            "direction": "neutral",

            "signal": "HOLD",

            "confidence": 0.0,

            "current_price": None,

            "entry": None,

            "stop_loss": None,

            "take_profit": None,

            "risk_reward": 0.0,

            "forecast": [],

            "patterns": [reason],

            "support": None,

            "resistance": None,

            "atr": 0.0,

            "generated_at": datetime.now(timezone.utc).isoformat(),

        }





trade_plan_service = TradePlanService()
