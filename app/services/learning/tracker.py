import json

import logging

from typing import Any, Dict, Optional



from sqlalchemy import text



from app.core.database import TimescaleSession



logger = logging.getLogger(__name__)





class HistoryTracker:

    """Persists model/analysis/trade events for later review and learning."""



    @classmethod

    async def log_image_analysis(

        cls,

        session,

        image_bytes: bytes,

        analysis_result: Any,

        model_version: str,

    ) -> None:

        try:

            payload = json.dumps(analysis_result, default=str)

        except Exception:  # noqa: BLE001

            payload = "{}"

        stmt = text(

            """

            INSERT INTO image_analyses

                (created_at, model_version, image_size, analysis_result)

            VALUES (now(), :model_version, :image_size, :analysis_result::jsonb)

            """

        )

        await session.execute(

            stmt,

            {

                "model_version": model_version,

                "image_size": len(image_bytes or b""),

                "analysis_result": payload,

            },

        )

        await session.commit()

        logger.info("Logged image analysis (%s bytes)", len(image_bytes or b""))



    @classmethod

    async def log_prediction(

        cls,

        session,

        instrument: str,

        signal: str,

        confidence: float,

        model_version: str = "v3.2",

    ) -> None:

        stmt = text(

            """

            INSERT INTO predictions

                (created_at, instrument, signal, confidence, model_version)

            VALUES (now(), :instrument, :signal, :confidence, :model_version)

            """

        )

        await session.execute(

            stmt,

            {

                "instrument": instrument,

                "signal": signal,

                "confidence": float(confidence),

                "model_version": model_version,

            },

        )

        await session.commit()



    @classmethod

    async def log_trade(

        cls,

        session,

        instrument: str,

        side: str,

        size: float,

        price: float,

        pnl: Optional[float] = None,

    ) -> None:

        stmt = text(

            """

            INSERT INTO trades

                (created_at, instrument, side, size, price, pnl)

            VALUES (now(), :instrument, :side, :size, :price, :pnl)

            """

        )

        await session.execute(

            stmt,

            {

                "instrument": instrument,

                "side": side,

                "size": float(size),

                "price": float(price),

                "pnl": None if pnl is None else float(pnl),

            },

        )

        await session.commit()
