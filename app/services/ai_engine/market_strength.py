import logging

from datetime import datetime, timezone

from typing import Any, Dict, List, Optional



import numpy as np

import pandas as pd



from app.services.data_ingestion.historical import HistoricalDataFetcher, DataUnavailable





logger = logging.getLogger(__name__)





class MarketStrengthService:

    """Compute market-strength indicators for a symbol.



    Returns classic trend/mean-reversion/momentum reads (ADX, RSI, MACD,

    Bollinger %B, ATR%, volume ratio) plus a **composite strength score**

    (0-100) and a **bias** (bullish / bearish / neutral) so the UI can show a

    single at-a-glance "how strong / which way" read. Degrades gracefully:

    returns zeros if there isn't enough candle history.

    """



    def __init__(self) -> None:

        self.fetcher = HistoricalDataFetcher()



    async def compute(

        self,

        instrument: str,

        timeframe: str = "5m",

        limit: int = 500,

        lookback_days: int = 7,

    ) -> Dict[str, Any]:

        end = datetime.now(timezone.utc)

        start = end - pd.Timedelta(days=lookback_days)

        try:

            candles = await self.fetcher.get_candles(instrument, timeframe, start, end, limit)

        except DataUnavailable:

            raise

        if not candles or len(candles) < 30:

            return self._empty(instrument, timeframe)



        df = pd.DataFrame(candles)

        close = pd.to_numeric(df["close"], errors="coerce").astype(float)

        high = pd.to_numeric(df["high"], errors="coerce").astype(float)

        low = pd.to_numeric(df["low"], errors="coerce").astype(float)

        vol = pd.to_numeric(df["volume"], errors="coerce").astype(float)

        times = [int(c["time"]) for c in candles]



        adx, plus_di, minus_di = self._adx(high, low, close, 14)

        rsi = self._rsi(close, 14)

        macd_line, signal, hist = self._macd(close)

        upper, lower, mid = self._bollinger(close, 20, 2)

        atr = self._atr(high, low, close, 14)

        atr_pct = float(atr / close.iloc[-1]) if close.iloc[-1] else 0.0

        vol_ratio = float(vol.iloc[-1] / vol.rolling(20).mean().iloc[-1]) if vol.rolling(20).mean().iloc[-1] else 1.0



        # Per-bar composite strength (0-100).

        sma20 = close.rolling(20).mean()

        conv = (

            np.sign(close - sma20).fillna(0)

            + np.sign(hist.fillna(0))

        ) / 2.0

        conv = conv.clip(-1, 1)

        strength_series = (adx * (0.5 + 0.5 * conv)).clip(0, 100)



        adx_last = float(adx.iloc[-1])

        rsi_last = float(rsi.iloc[-1])

        bb_pct_b = float(((close.iloc[-1] - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1]))

                         if (upper.iloc[-1] - lower.iloc[-1]) != 0 else 0.5)

        bandwidth = float(((upper.iloc[-1] - lower.iloc[-1]) / mid.iloc[-1])

                          if mid.iloc[-1] else 0.0)



        # Bias from direction of trend + momentum.

        bias = "neutral"

        if adx_last >= 20:

            if close.iloc[-1] > sma20.iloc[-1] and plus_di.iloc[-1] >= minus_di.iloc[-1]:

                bias = "bullish"

            elif close.iloc[-1] < sma20.iloc[-1] and minus_di.iloc[-1] >= plus_di.iloc[-1]:

                bias = "bearish"

        trend_label = (

            "strong uptrend" if (adx_last >= 25 and bias == "bullish")

            else "strong downtrend" if (adx_last >= 25 and bias == "bearish")

            else "trending" if adx_last >= 20

            else "ranging / weak"

        )

        strength = float(strength_series.iloc[-1])



        def pack(series):

            return [

                None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(float(v), 4)

                for v in series.tolist()

            ]



        return {

            "instrument": instrument.upper(),

            "timeframe": timeframe,

            "strength": round(strength, 1),

            "bias": bias,

            "trend": trend_label,

            "adx": round(adx_last, 2),

            "plus_di": round(float(plus_di.iloc[-1]), 2),

            "minus_di": round(float(minus_di.iloc[-1]), 2),

            "rsi": round(rsi_last, 2),

            "macd": {

                "macd": round(float(macd_line.iloc[-1]), 6),

                "signal": round(float(signal.iloc[-1]), 6),

                "hist": round(float(hist.iloc[-1]), 6),

            },

            "bollinger": {"pct_b": round(bb_pct_b, 4), "bandwidth": round(bandwidth, 4)},

            "atr_pct": round(atr_pct, 4),

            "volume_ratio": round(vol_ratio, 2),

            "times": times,

            "adx_series": pack(adx),

            "strength_series": pack(strength_series),

            "generated_at": datetime.now(timezone.utc).isoformat(),

        }



    # ------------------------------------------------------------------ #

    @staticmethod

    def _adx(high, low, close, period=14):

        if len(close) <= period * 2:

            n = len(close)

            return (

                pd.Series([0.0] * n), pd.Series([0.0] * n), pd.Series([0.0] * n)

            )

        prev_close = close.shift(1)

        tr = pd.concat(

            [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1

        ).max(axis=1)

        up = high - high.shift(1)

        down = low.shift(1) - low

        plus_dm = up.where((up > down) & (up > 0), 0.0)

        minus_dm = down.where((down > up) & (down > 0), 0.0)



        atr = tr.rolling(period).mean()

        plus_di = 100 * (plus_dm.rolling(period).mean() / atr).fillna(0)

        minus_di = 100 * (minus_dm.rolling(period).mean() / atr).fillna(0)

        dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)).fillna(0)

        adx = dx.rolling(period).mean().fillna(0)

        return adx, plus_di, minus_di



    @staticmethod

    def _rsi(close, period=14):

        if len(close) <= period:

            return pd.Series([50.0] * len(close))

        delta = close.diff()

        gain = delta.clip(lower=0).rolling(period).mean()

        loss = (-delta.clip(upper=0)).rolling(period).mean()

        rs = gain / loss.replace(0, np.nan)

        return (100 - (100 / (1 + rs))).fillna(50)



    @staticmethod

    def _macd(close, fast=12, slow=26, signal_p=9):

        ema_f = close.ewm(span=fast, adjust=False).mean()

        ema_s = close.ewm(span=slow, adjust=False).mean()

        macd_line = ema_f - ema_s

        signal = macd_line.ewm(span=signal_p, adjust=False).mean()

        hist = macd_line - signal

        return macd_line, signal, hist



    @staticmethod

    def _bollinger(close, period=20, num_std=2):

        mid = close.rolling(period).mean()

        std = close.rolling(period).std()

        upper = mid + num_std * std

        lower = mid - num_std * std

        return upper, lower, mid



    @staticmethod

    def _atr(high, low, close, period=14):

        if len(high) < 2:

            return 0.0

        prev_close = close.shift(1)

        tr = pd.concat(

            [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1

        ).max(axis=1)

        return float(tr.rolling(period).mean().iloc[-1])



    @staticmethod

    def _empty(instrument: str, timeframe: str) -> Dict[str, Any]:

        return {

            "instrument": instrument.upper(),

            "timeframe": timeframe,

            "strength": 0.0,

            "bias": "neutral",

            "trend": "insufficient history",

            "adx": 0.0,

            "plus_di": 0.0,

            "minus_di": 0.0,

            "rsi": 50.0,

            "macd": {"macd": 0.0, "signal": 0.0, "hist": 0.0},

            "bollinger": {"pct_b": 0.5, "bandwidth": 0.0},

            "atr_pct": 0.0,

            "volume_ratio": 1.0,

            "times": [],

            "adx_series": [],

            "strength_series": [],

            "generated_at": datetime.now(timezone.utc).isoformat(),

        }





market_strength_service = MarketStrengthService()
