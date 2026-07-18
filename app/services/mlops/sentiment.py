import logging

from typing import Dict, Any, List, Optional



from app.core.config import settings



logger = logging.getLogger(__name__)





class SentimentEngine:

    """FinBERT sentiment analysis for news / social text.



    The HuggingFace pipeline is loaded lazily inside `initialize()` so this

    module can always be imported even when `transformers`/model weights are

    unavailable (e.g. in constrained environments). If loading fails, the engine

    degrades to a neutral fallback instead of crashing the app.

    """



    def __init__(self) -> None:

        self.pipeline: Optional[Any] = None



    async def initialize(self) -> None:

        try:

            from transformers import pipeline as hf_pipeline



            device = settings.FINBERT_DEVICE

            # transformers expects an int device index; "cpu" -> -1

            device_arg = -1 if str(device).lower() == "cpu" else device

            self.pipeline = hf_pipeline(

                "sentiment-analysis",

                model=settings.FINBERT_MODEL,

                device=device_arg,

                top_k=1,

            )

            logger.info("FinBERT sentiment pipeline loaded (%s)", settings.FINBERT_MODEL)

        except Exception as e:  # noqa: BLE001

            logger.warning("Sentiment model unavailable, degrading to neutral: %s", e)

            self.pipeline = None



    async def analyze(self, texts: List[str]) -> List[Dict[str, Any]]:

        if not texts:

            return []

        if self.pipeline is None:

            return [

                {"label": "neutral", "score": 0.5, "text": t[:200]} for t in texts

            ]

        try:

            raw = self.pipeline(texts[:32])

            return [

                {"label": r["label"], "score": float(r["score"]), "text": t[:200]}

                for r, t in zip(raw, texts)

            ]

        except Exception as e:  # noqa: BLE001

            logger.error("Sentiment analysis failed: %s", e)

            return [

                {"label": "neutral", "score": 0.5, "text": t[:200]} for t in texts

            ]





    def analyze_sync(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Synchronous variant for non-event-loop contexts (e.g. curated news).

        HuggingFace pipelines are themselves synchronous callables, so this
        avoids spawning an event loop. Degrades to neutral when unavailable.
        """
        if not texts:
            return []
        if self.pipeline is None:
            return [{"label": "neutral", "score": 0.5, "text": t[:200]} for t in texts]
        try:
            raw = self.pipeline(texts[:32])
            return [
                {"label": r["label"], "score": float(r["score"]), "text": t[:200]}
                for r, t in zip(raw, texts)
            ]
        except Exception as e:  # noqa: BLE001
            logger.error("Sync sentiment failed: %s", e)
            return [{"label": "neutral", "score": 0.5, "text": t[:200]} for t in texts]


sentiment_engine = SentimentEngine()
