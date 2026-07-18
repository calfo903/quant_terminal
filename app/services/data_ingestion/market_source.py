import asyncio

import logging

import time

from abc import ABC, abstractmethod

from typing import Any, Dict, List, Optional, Set



from app.core.config import settings

from app.core.database import get_redis

from app.services.data_ingestion.tick_writer import publish_tick



logger = logging.getLogger(__name__)





def _num(v: Any) -> float:

    try:

        return float(v) if v is not None else 0.0

    except (TypeError, ValueError):

        return 0.0





def _normalize_live_rates(item: Dict[str, Any], symbol_set: Set[str]) -> Optional[Dict[str, Any]]:

    """Normalize a Live-Rates quote into the shared tick schema."""

    cur = str(item.get("currency") or item.get("symbol") or "")

    sym = cur.replace("/", "").replace("_", "").upper()

    if sym not in symbol_set:

        return None

    price = item.get("close")

    if price is None:

        price = item.get("rate")

    if price is None:

        price = item.get("price")

    price = _num(price)

    if price <= 0:

        return None

    ts = item.get("timestamp")

    try:

        ts = int(ts)

    except (TypeError, ValueError):

        ts = int(time.time() * 1000)

    return {

        "instrument": sym,

        "timestamp": ts,

        "price": price,

        "quantity": 0.0,

        "is_buy": None,

        "received_at": time.time(),

        "bid": _num(item.get("bid")),

        "ask": _num(item.get("ask")),

        "source": "live_rates",

    }





class MarketSource(ABC):

    """Pluggable real-time market data source.



    Concrete sources normalize their quotes into the same tick schema Binance

    uses (``instrument, timestamp(ms), price, quantity, is_buy, received_at``)

    and push them through ``publish_tick`` so the rest of the pipeline (WS

    dispatcher, latest price, trade-plan, indicators) is source-agnostic.

    """



    name: str = "base"



    @abstractmethod

    async def start(self) -> None:

        """Run the streaming/polling loop until ``stop()`` is called."""



    @abstractmethod

    async def stop(self) -> None:

        """Signal the loop to exit."""





class LiveRatesSource(MarketSource):

    """Live-Rates free forex/commodity source over REST polling.



    Uses the REST endpoint (no new heavy deps — ``httpx`` is already present).

    Polls all configured symbols in one request and publishes each normalized

    quote to Redis. A WebSocket/socket.io variant (``LiveRatesWsSource``) can be

    selected via ``FOREX_SOURCE=live_rates_ws`` for true sub-second updates.

    """



    name = "live_rates"
    BASE_URL = "https://www.live-rates.com/api/price"

    def __init__(

        self,

        symbols: List[str],

        api_key: str = "",

        poll_interval: float = 2.0,

    ) -> None:

        self.symbols = [s.upper() for s in symbols]

        self.symbol_set = set(self.symbols)

        self.api_key = api_key

        self.poll_interval = max(0.5, float(poll_interval))

        self._running = False



    async def start(self) -> None:

        if not self.symbols:

            logger.info("LiveRates: no symbols configured; not starting")

            return

        self._running = True

        import httpx  # lazy: only needed when this source is actually used



        params = {"rate": ",".join(self.symbols)}

        if self.api_key:

            params["key"] = self.api_key



        logger.info("LiveRates REST stream starting for %d symbols", len(self.symbols))

        async with httpx.AsyncClient(timeout=10.0) as client:

            while self._running:

                try:

                    resp = await client.get(self.BASE_URL, params=params)

                    if resp.status_code == 200:

                        data = resp.json()

                        items = data if isinstance(data, list) else (

                            data.get("data") or data.get("quotes") or []

                        )

                        for item in items:

                            tick = _normalize_live_rates(item, self.symbol_set)

                            if tick:

                                await publish_tick(get_redis(), tick)

                    else:

                        logger.warning("LiveRates HTTP %s", resp.status_code)

                except Exception as e:  # noqa: BLE001

                    logger.warning("LiveRates poll error: %s", e)

                # Interruptible sleep (responds to stop() promptly).

                elapsed = 0.0

                while self._running and elapsed < self.poll_interval:

                    await asyncio.sleep(0.1)

                    elapsed += 0.1



    async def stop(self) -> None:

        self._running = False





class LiveRatesWsSource(MarketSource):

    """Live-Rates free forex/commodity source over WebSocket (socket.io).



    True push (sub-second) alternative to the REST poller. Requires the

    ``python-socketio[client]`` package (lazy-imported; the app still runs

    without it — this source just logs and idles). Event/subscribe names match

    Live-Rates' documented socket.io stream; tweak ``_on_data`` if your account

    uses different event names.

    """



    name = "live_rates_ws"
    WS_URL = "https://www.live-rates.com"

    def __init__(

        self,

        symbols: List[str],

        api_key: str = "",

        poll_interval: float = 2.0,

    ) -> None:

        self.symbols = [s.upper() for s in symbols]

        self.symbol_set = set(self.symbols)

        self.api_key = api_key

        self.poll_interval = poll_interval

        self._running = False

        self._sio = None



    async def start(self) -> None:

        try:

            import socketio  # lazy: optional dependency

        except ImportError:

            logger.warning(

                "python-socketio not installed; LiveRates WS disabled. "

                "Run: pip install 'python-socketio[client]'"

            )

            while self._running:

                await asyncio.sleep(60)

            return



        self._running = True

        sio = socketio.AsyncClient()

        self._sio = sio



        @sio.event

        async def connect() -> None:  # noqa: ANN202

            logger.info("LiveRates WS connected")

            try:

                sio.emit("subscribe", {"rate": ",".join(self.symbols)})

                if self.api_key:

                    sio.emit("auth", {"key": self.api_key})

            except Exception as e:  # noqa: BLE001

                logger.warning("LiveRates WS subscribe failed: %s", e)



        @sio.event

        async def disconnect() -> None:  # noqa: ANN202

            logger.info("LiveRates WS disconnected")



        async def _handle(data: Any) -> None:

            items = data if isinstance(data, list) else (data or {})

            items = items.get("data") or items.get("quotes") or items

            if not isinstance(items, list):

                items = [items]

            for item in items:

                tick = _normalize_live_rates(item, self.symbol_set)

                if tick:

                    await publish_tick(get_redis(), tick)



        for _evt in ("tick", "price", "rates", "message", "quote"):

            sio.on(_evt, _handle)



        logger.info("LiveRates WS stream starting for %d symbols", len(self.symbols))

        try:

            await sio.connect(self.WS_URL, transports=["websocket"], socketio_path="/socket.io")

            while self._running:

                await sio.wait()

                if not self._running:

                    break

                await asyncio.sleep(1)

        except Exception as e:  # noqa: BLE001

            logger.warning("LiveRates WS error: %s", e)

        finally:

            self._running = False



    async def stop(self) -> None:

        self._running = False

        if self._sio is not None:

            try:

                await self._sio.disconnect()

            except Exception:  # noqa: BLE001

                pass
