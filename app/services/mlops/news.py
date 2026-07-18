import asyncio

import json

import logging

from datetime import datetime, timezone

from typing import Any, Dict, List, Optional



from app.core.config import settings

from app.core.database import get_redis

from app.services.mlops.sentiment import sentiment_engine



logger = logging.getLogger(__name__)



# Curated "important news" used when no live news feed is configured/reachable.

# Published times are computed relative to "now" so the sidebar always looks

# fresh even fully offline. Importance 1 (low) .. 5 (market-moving).

_CURATED: List[Dict[str, Any]] = [

    {

        "title": "Gold (XAUUSD) holds near record highs as Fed cut bets build",

        "source": "Quant Terminal Wire",

        "url": "",

        "summary": "Spot gold consolidates after a strong run; softer US yields and "

        "renewed safe-haven demand keep XAUUSD bid into the next print.",

        "category": "commodity",

        "importance": 5,

        "symbols": ["XAUUSD"],

    },

    {

        "title": "Bitcoin reclaims key resistance as spot ETF inflows resume",

        "source": "Quant Terminal Wire",

        "url": "",

        "summary": "BTC led crypto majors higher after a week of net ETF inflows; "

        "derivatives funding normalises.",

        "category": "crypto",

        "importance": 4,

        "symbols": ["BTCUSDT"],

    },

    {

        "title": "EUR/USD tests 1.09 as ECB officials signal data-dependent path",

        "source": "Quant Terminal Wire",

        "url": "",

        "summary": "The euro stays firm against the dollar ahead of tier-1 eurozone "

        "inflation data; vol compressed near recent lows.",

        "category": "forex",

        "importance": 4,

        "symbols": ["EURUSD"],

    },

    {

        "title": "USD/JPY under scrutiny as officials warn on excessive moves",

        "source": "Quant Terminal Wire",

        "url": "",

        "summary": "Intervention rhetoric keeps yen crosses two-way; carry unwinds "

        "remain the key tail risk for USDJPY.",

        "category": "forex",

        "importance": 4,

        "symbols": ["USDJPY"],

    },

    {

        "title": "Ethereum gas fees drop to multi-month lows after upgrade",

        "source": "Quant Terminal Wire",

        "url": "",

        "summary": "L2 activity absorbs mainnet load, lowering costs and supporting "

        "broader altcoin sentiment.",

        "category": "crypto",

        "importance": 3,

        "symbols": ["ETHUSDT"],

    },

    {

        "title": "GBP firm as UK wage growth cools slower than expected",

        "source": "Quant Terminal Wire",

        "url": "",

        "summary": "Sterling bid after labour data; BoE cut expectations pushed back, "

        "supporting GBPUSD and GBPJPY.",

        "category": "forex",

        "importance": 3,

        "symbols": ["GBPUSD", "GBPJPY"],

    },

    {

        "title": "Solana network activity ticks up on memecoin rotation",

        "source": "Quant Terminal Wire",

        "url": "",

        "summary": "On-chain volumes recover; SOL outperforms majors on renewed "

        "risk appetite.",

        "category": "crypto",

        "importance": 3,

        "symbols": ["SOLUSDT"],

    },

    {

        "title": "US dollar index drifts as traders weigh soft-landing odds",

        "source": "Quant Terminal Wire",

        "url": "",

        "summary": "DXY rangebound; AUDUSD and NZDUSD sensitive to risk sentiment and "

        "commodity prices.",

        "category": "forex",

        "importance": 2,

        "symbols": ["AUDUSD", "NZDUSD"],

    },

    {

        "title": "XRP volatility compresses ahead of regulatory headline risk",

        "source": "Quant Terminal Wire",

        "url": "",

        "summary": "Range trade dominates XRPUSDT; options skew flattens into the "

        "next catalyst.",

        "category": "crypto",

        "importance": 2,

        "symbols": ["XRPUSDT"],

    },

    {

        "title": "Oil and gold correlation rises on geopolitical risk premium",

        "source": "Quant Terminal Wire",

        "url": "",

        "summary": "Cross-asset safe-haven bid supports precious metals; macro desk "

        "flags event risk into the weekend.",

        "category": "macro",

        "importance": 3,

        "symbols": ["XAUUSD"],

    },

]





class NewsService:

    """Aggregates the latest important financial news.



    Tries an optional live JSON feed (``settings.NEWS_API_URL``) and scores each

    headline with the FinBERT sentiment engine. When no feed is configured or

    the network is unavailable it degrades gracefully to a curated set so the

    sidebar is never empty. Results are cached in Redis for ``NEWS_CACHE_TTL``.

    """



    CACHE_KEY = "news:latest"



    async def get_latest(

        self, limit: int = 20, category: Optional[str] = None

    ) -> Dict[str, Any]:

        r = get_redis()



        cached = None

        if r is not None:

            try:

                cached = await r.get(self.CACHE_KEY)

            except Exception as e:  # noqa: BLE001

                logger.debug("news cache read failed: %s", e)



        if cached:

            items = json.loads(cached)

            source_kind = "cache"

        else:

            items, source_kind = await self._fetch()

            # Score curated headlines with FinBERT off the event loop so the

            # (synchronous) pipeline call never blocks request handling.

            if source_kind == "curated":

                try:

                    titles = [i["title"] for i in items]

                    scores = await asyncio.to_thread(

                        sentiment_engine.analyze_sync, titles

                    )

                    for it, sc in zip(items, scores):

                        it["sentiment"] = sc.get("label", "neutral")

                        it["sentiment_score"] = float(sc.get("score", 0.5))

                except Exception as e:  # noqa: BLE001

                    logger.debug("curated news sentiment skipped: %s", e)

            if r is not None:

                try:

                    await r.set(

                        self.CACHE_KEY,

                        json.dumps(items, default=str),

                        ex=settings.NEWS_CACHE_TTL,

                    )

                except Exception as e:  # noqa: BLE001

                    logger.debug("news cache write failed: %s", e)



        if category:

            items = [i for i in items if i.get("category") == category]

        items = sorted(

            items,

            key=lambda i: (i.get("importance", 0), i.get("published_at", "")),

            reverse=True,

        )[: max(1, min(limit, 100))]



        return {

            "items": items,

            "source": source_kind,

            "count": len(items),

            "generated_at": datetime.now(timezone.utc).isoformat(),

        }



    async def _fetch(self) -> (List[Dict[str, Any]], str):

        if settings.NEWS_API_URL:

            try:

                items = await self._fetch_live()

                if items:

                    return items, "live"

            except Exception as e:  # noqa: BLE001

                logger.warning("Live news fetch failed, using curated: %s", e)

        return self._curated_items(), "curated"



    async def _fetch_live(self) -> List[Dict[str, Any]]:

        import httpx



        headers = {}

        if settings.NEWS_API_KEY:

            headers["Authorization"] = f"Bearer {settings.NEWS_API_KEY}"

        async with httpx.AsyncClient(timeout=5.0, headers=headers) as client:

            resp = await client.get(settings.NEWS_API_URL)

            resp.raise_for_status()

            data = resp.json()



        raw_list = data

        if isinstance(data, dict):

            raw_list = data.get("articles") or data.get("items") or []

        headlines = [str(h.get("title", "")) for h in raw_list if h.get("title")]

        scores = await sentiment_engine.analyze(headlines) if headlines else []

        items: List[Dict[str, Any]] = []

        for h, sc in zip(raw_list, scores):

            items.append(self._normalise(h, sc))

        return items



    def _normalise(self, h: Dict[str, Any], sc: Dict[str, Any]) -> Dict[str, Any]:

        return {

            "id": h.get("id") or h.get("url") or str(hash(str(h.get("title")))),

            "title": h.get("title", ""),

            "source": (

                h.get("source", {}).get("name")

                if isinstance(h.get("source"), dict)

                else h.get("source", "news")

            ),

            "url": h.get("url") or h.get("link") or "",

            "summary": h.get("description") or h.get("summary") or "",

            "category": h.get("category", "macro"),

            "importance": int(h.get("importance", 2)),

            "symbols": h.get("symbols", []),

            "published_at": h.get("publishedAt")

            or h.get("published_at")

            or datetime.now(timezone.utc).isoformat(),

            "sentiment": sc.get("label", "neutral"),

            "sentiment_score": float(sc.get("score", 0.5)),

        }



    def _curated_items(self) -> List[Dict[str, Any]]:

        now = datetime.now(timezone.utc)

        items: List[Dict[str, Any]] = []

        for idx, base in enumerate(_CURATED):

            minutes_ago = idx * 7 + 3

            published = now.timestamp() - minutes_ago * 60

            item = dict(base)

            item["id"] = f"curated-{idx}"

            item["published_at"] = datetime.fromtimestamp(

                published, tz=timezone.utc

            ).isoformat()

            item["sentiment"] = "neutral"

            item["sentiment_score"] = 0.5

            items.append(item)

        # Sentiment is (re)scored by get_latest() off the event loop so the

        # synchronous FinBERT pipeline call never blocks request handling.

        return items





news_service = NewsService()
