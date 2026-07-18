import asyncio
import logging

import time

from typing import Any, Dict, List, Optional



import numpy as np

import pandas as pd



from app.core.config import settings

from app.services.ai_engine.model_registry import model_registry



logger = logging.getLogger(__name__)





class Predictor:

    """Produces a trading signal + confidence + features for an instrument.



    It computes robust technical features (close, ATR, spread) and combines a

    momentum/volatility heuristic with any loaded ML model (TFT / LightGBM) when

    available. Everything degrades gracefully if models or data are missing.

    """



    def __init__(self) -> None:

        self.model_registry = model_registry



    # ------------------------------------------------------------------ #

    # Public API (matches call sites in charts.py / websockets.py)

    # ------------------------------------------------------------------ #

    async def predict(

        self,

        instrument: str,

        candles_df: pd.DataFrame,

        ticks: List[Dict[str, Any]],

        bias: float = 0.0,

    ) -> Dict[str, Any]:

        # Heavy pandas/NumPy feature engineering runs in a worker thread so it

        # never blocks the event loop (a single-process uvicorn would otherwise

        # stall every other request while a prediction is computed).

        features = await asyncio.to_thread(self._compute_features, candles_df, ticks)

        confidence, signal, direction, predicted_change = self._score(features, instrument)



        # Optional model-assisted adjustment (does not crash if model absent).

        model_out = await asyncio.to_thread(self._model_adjustment, instrument, features)

        if model_out is not None:

            confidence = float(np.clip(0.5 * confidence + 0.5 * model_out, 0.0, 1.0))



        confidence = float(np.clip(confidence + bias, 0.0, 1.0))



        return {

            "instrument": instrument,

            "signal": signal,

            "direction": direction,

            "confidence": round(confidence, 4),

            "predicted_change_pct": round(float(predicted_change), 6),

            "features": features,

            "timestamp": int(time.time()),

        }



    # ------------------------------------------------------------------ #

    # Feature engineering

    # ------------------------------------------------------------------ #

    def _compute_features(

        self, df: pd.DataFrame, ticks: List[Dict[str, Any]]

    ) -> Dict[str, float]:

        features: Dict[str, float] = {

            "close": 0.0,

            "atr": 0.0,

            "spread": 0.0,

            "volatility": 0.0,

            "momentum": 0.0,

            "rsi": 50.0,

        }



        if df is not None and len(df) > 0:

            close = pd.to_numeric(df["close"], errors="coerce").astype(float)

            high = pd.to_numeric(df["high"], errors="coerce").astype(float)

            low = pd.to_numeric(df["low"], errors="coerce").astype(float)

            features["close"] = float(close.iloc[-1])

            features["atr"] = self._atr(high, low, close, period=14)

            returns = close.pct_change().dropna()

            if len(returns) > 1:

                features["volatility"] = float(returns.std())

                features["momentum"] = float(returns.tail(5).sum())

                features["rsi"] = float(self._rsi(close, period=14))



        if ticks:

            prices = [float(t.get("price", 0.0)) for t in ticks if t.get("price")]

            if prices:

                hi, lo = max(prices), min(prices)

                mid = (hi + lo) / 2.0

                features["spread"] = float(hi - lo)

                # If no candle close available, fall back to last tick price.

                if features["close"] == 0.0:

                    features["close"] = float(prices[-1])



        return features



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

    def _rsi(close: pd.Series, period: int = 14) -> float:

        if len(close) <= period:

            return 50.0

        delta = close.diff()

        gain = delta.clip(lower=0).rolling(period).mean()

        loss = (-delta.clip(upper=0)).rolling(period).mean()

        rs = gain / loss.replace(0, np.nan)

        rsi = 100 - (100 / (1 + rs))

        return float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0



    # ------------------------------------------------------------------ #

    # Scoring

    # ------------------------------------------------------------------ #

    def _score(self, f: Dict[str, float], instrument: str):

        # Momentum and RSI bias.

        momentum = f["momentum"]

        rsi = f["rsi"]

        direction = 1 if momentum >= 0 else -1

        signal = "BUY" if direction > 0 else "SELL"



        # Confidence grows with conviction of momentum and distance from RSI extremes.

        conviction = abs(momentum) * 100.0

        rsi_edge = abs(rsi - 50.0) / 50.0  # 0..1

        confidence = float(np.clip(0.4 * conviction + 0.4 * rsi_edge + 0.1, 0.0, 1.0))



        predicted_change = momentum * 100.0

        return confidence, signal, direction, predicted_change



    def _model_adjustment(self, instrument: str, f: Dict[str, float]) -> Optional[float]:

        try:

            if self.model_registry.lgbm_model is not None:

                out = self.model_registry.predict_lgbm(

                    {

                        "close": f["close"],

                        "atr": f["atr"],

                        "spread": f["spread"],

                        "volatility": f["volatility"],

                        "momentum": f["momentum"],

                        "rsi": f["rsi"],

                    }

                )

                pred = float(out.get("prediction", 0.0))

                # Map signed prediction to a 0..1 confidence with sign = direction.

                return float(np.clip(0.5 + 0.5 * np.sign(pred) * min(abs(pred), 1.0), 0.0, 1.0))

        except Exception as e:  # noqa: BLE001

            logger.debug("Model adjustment skipped: %s", e)

        return None





predictor = Predictor()
