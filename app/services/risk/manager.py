import logging

import time

from typing import Dict, Any, Optional



from app.core.config import settings



logger = logging.getLogger(__name__)



# Default maximum accepted spread as a fraction of price (10 bps).

MAX_SPREAD_PCT = 0.001





class RiskManager:

    """Pre-trade risk checks and position sizing."""



    def __init__(self) -> None:

        self._breached_at: Optional[float] = None



    def trigger_circuit_breaker(self) -> None:

        """Halt trading for the configured cooldown window."""

        self._breached_at = time.time()

        logger.warning("Circuit breaker TRIGGERED at %s", self._breached_at)



    def _breaker_active(self) -> bool:

        if self._breached_at is None:

            return False

        cooldown = settings.CIRCUIT_BREAKER_COOLDOWN_HOURS * 3600

        return (time.time() - self._breached_at) < cooldown



    async def check_all(

        self,

        current_equity: float,

        signal_confidence: float,

        atr_pct: float,

        spread_pct: float,

    ) -> Dict[str, Any]:

        reasons: List[str] = []

        allowed = True



        if signal_confidence < settings.MIN_CONFIDENCE_THRESHOLD:

            allowed = False

            reasons.append(

                f"confidence {signal_confidence:.3f} < min "

                f"{settings.MIN_CONFIDENCE_THRESHOLD}"

            )



        if atr_pct > settings.TARGET_VOLATILITY:

            allowed = False

            reasons.append(

                f"volatility {atr_pct:.4f} exceeds target "

                f"{settings.TARGET_VOLATILITY}"

            )



        if spread_pct > MAX_SPREAD_PCT:

            allowed = False

            reasons.append(f"spread {spread_pct:.4f} too wide")



        if self._breaker_active():

            allowed = False

            reasons.append("circuit breaker active")



        if not allowed:

            logger.info("Trade REJECTED: %s", reasons)



        return {

            "allowed": allowed,

            "reasons": reasons,

            "confidence": signal_confidence,

        }



    def size_position(

        self,

        equity: float,

        atr: float,

        price: float,

        confidence: float,

    ) -> float:

        """Volatility-scaled position size (units of the instrument).



        Risk per trade is a fixed fraction of equity, divided by ATR (the per-unit

        risk), then scaled by model confidence.

        """

        if atr <= 0 or price <= 0:

            return 0.0

        risk_capital = equity * settings.RISK_PER_TRADE_PCT

        raw_size = risk_capital / atr

        sized = raw_size * float(confidence)

        return round(sized, 4)





risk_manager = RiskManager()
