import logging

import re

from typing import Any, Dict, List, Optional



from app.core.config import settings



logger = logging.getLogger(__name__)



SYMBOL_RE = re.compile(r"\b(BTC|ETH|SOL|XRP|USDT?|EUR|GBP|JPY)\b", re.IGNORECASE)
PATTERN_KEYWORDS = {
    "support": "Support",
    "resistance": "Resistance",
    "breakout": "Breakout",
    "breakdown": "Breakdown",
    "bullish": "Bullish",
    "bearish": "Bearish",
    "trend": "Trend",
    "reversal": "Reversal",
    "head and shoulders": "Head & Shoulders",
    "double top": "Double Top",
    "double bottom": "Double Bottom",
}

# Forex pairs are two 3-letter currency codes, e.g. EURUSD, GBPJPY.
FOREX_PAIR_RE = re.compile(r"\b([A-Z]{3})([A-Z]{3})\b")
_MAJORS = {s.strip().upper() for s in settings.FOREX_MAJORS.split(",") if s.strip()}
_MINORS = {s.strip().upper() for s in settings.FOREX_MINORS.split(",") if s.strip()}
_COMMODITIES = {s.strip().upper() for s in settings.COMMODITIES.split(",") if s.strip()}





class ChartAnalyzer:

    """OCR + lightweight pattern heuristics for uploaded chart images.



    Heavy CV libraries (opencv, pytesseract) are imported lazily so the module

    always imports; if they are missing the analyzer returns a metadata-only

    result instead of raising.

    """



    def __init__(self) -> None:

        self._cv2 = None

        self._pytesseract = None

        self._np = None



    def _ensure(self) -> None:

        if self._cv2 is None:

            import cv2  # type: ignore

            self._cv2 = cv2

        if self._np is None:

            import numpy as np

            self._np = np

        if self._pytesseract is None:

            import pytesseract  # type: ignore

            self._pytesseract = pytesseract



    async def analyze(self, image_bytes: bytes) -> Dict[str, Any]:

        if not image_bytes:

            return self._empty("empty image")



        try:

            self._ensure()

        except Exception as e:  # noqa: BLE001

            logger.warning("Vision libraries unavailable, metadata-only: %s", e)

            return {

                "status": "partial",

                "detected_patterns": [],

                "ocr_text": "",

                "symbol": None,

                "sentiment": "neutral",

                "confidence": 0.0,

                "notes": ["vision libraries not installed"],

            }



        try:

            img = self._cv2.imdecode(

                self._np.frombuffer(image_bytes, dtype=self._np.uint8),

                self._cv2.IMREAD_COLOR,

            )

            if img is None:

                return self._empty("could not decode image")



            ocr_text = self._pytesseract.image_to_string(img) or ""

            patterns = self._detect_patterns(ocr_text, img)

            symbol = self._detect_symbol(ocr_text)



            # Classify the detected symbol into market + (for forex) major/minor.

            market = "crypto"
            pair_type = None
            if symbol:
                if symbol in _COMMODITIES:
                    market, pair_type = "commodity", "metal"
                elif symbol in _MAJORS:
                    market, pair_type = "forex", "major"
                elif symbol in _MINORS:
                    market, pair_type = "forex", "minor"



            sentiment, confidence = self._classify(patterns, ocr_text)



            return {

                "status": "ok",

                "detected_patterns": patterns,

                "ocr_text": ocr_text.strip(),

                "symbol": symbol,

                "market": market,

                "pair_type": pair_type,

                "sentiment": sentiment,

                "confidence": confidence,

                "notes": [],

            }

        except Exception as e:  # noqa: BLE001

            logger.error("Chart analysis failed: %s", e, exc_info=True)

            return self._empty(f"analysis error: {e}")



    # ------------------------------------------------------------------ #

    def _detect_patterns(self, text: str, img) -> List[str]:

        found: List[str] = []

        low = text.lower()

        for key, label in PATTERN_KEYWORDS.items():

            if key in low and label not in found:

                found.append(label)

        return found



    def _detect_symbol(self, text: str) -> Optional[str]:

        # Forex pairs (two 3-letter codes) take priority over single tokens.

        m = FOREX_PAIR_RE.search(text)

        if m:

            return m.group(1) + m.group(2)

        m = SYMBOL_RE.search(text)

        return m.group(0).upper() if m else None



    def _classify(self, patterns: List[str], text: str) -> (str, float):

        low = text.lower()

        bull = any(p in ("Bullish", "Breakout", "Support") for p in patterns) or "buy" in low

        bear = any(p in ("Bearish", "Breakdown", "Resistance") for p in patterns) or "sell" in low

        if bull and not bear:

            return "bullish", 0.7

        if bear and not bull:

            return "bearish", 0.7

        if bull and bear:

            return "mixed", 0.5

        return "neutral", 0.4



    @staticmethod

    def _empty(reason: str) -> Dict[str, Any]:

        return {

            "status": "empty",

            "detected_patterns": [],

            "ocr_text": "",

            "symbol": None,

            "market": None,

            "pair_type": None,

            "sentiment": "neutral",

            "confidence": 0.0,

            "notes": [reason],

        }





chart_analyzer = ChartAnalyzer()
