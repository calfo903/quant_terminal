import logging

import re

from datetime import datetime, timezone

from typing import Any, Dict, List, Optional



from app.core.config import settings

from app.core.database import get_redis

from app.services.mlops.news import news_service
from app.services.ai_engine.market_strength import market_strength_service
from app.services.ai_engine.market_strength import market_strength_service

from app.services.mlops.sentiment import sentiment_engine

import base64

from app.services.ai_engine.llm import get_llm, LLMUnavailable
from app.services.image_analysis.analyzer import chart_analyzer
from app.services.ai_engine.trade_plan import trade_plan_service
from app.services.data_ingestion.historical import DataUnavailable



logger = logging.getLogger(__name__)

# System prompt for the LLM reasoning plane. The LLM only narrates the
# deterministic signals; it must never invent prices or levels.
ANALYST_SYSTEM = (
    "You are the Quant AI Terminal analyst. Write concise, professional "
    "market-read commentary for traders. Rules: use ONLY the facts provided; "
    "never invent prices, levels, or news; 2-4 sentences; end with "
    "'Not financial advice.' Keep it direct and non-hype."
)



# Forex-style pairs: two 3-letter currency/asset codes, e.g. EURUSD, XAUUSD.

_PAIR_RE = re.compile(r"\b([A-Z]{3})([A-Z]{3})\b")





class ChatAssistant:

    """Lightweight, data-aware trading assistant (no external LLM required).



    Understands a small set of natural-language intents (symbol lookup, risk

    settings, latest news, market sentiment) and answers using live Redis ticks,

    the FinBERT-scored news feed, and the risk configuration. Every path degrades

    gracefully: if Redis / DB / models are offline it still returns a helpful,

    coherent response instead of an error.

    """



    def suggestions(self) -> List[str]:

        return [

            "What can you do?",

            "List available markets",

            "Analyze XAUUSD",

            "What's the BTC sentiment?",

            "Show risk settings",

            "Latest important news",

        ]



    async def _maybe_llm(self, system: str, user: str) -> Optional[str]:
        """Best-effort LLM narration. Returns None if no backend is configured or
        all backends are unavailable, so callers keep their heuristic reply.

        The system prompt and user facts are passed as SEPARATE message roles
        (standard 6.1: instructions isolated from input). The returned text is
        treated as untrusted (standard 6.2): sanitized and length-capped.
        """
        try:
            llm = get_llm()
        except Exception:  # noqa: BLE001
            return None
        if llm is None:
            return None  # offline mode (no backend configured) - not an error
        try:
            text = await llm.complete(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ]
            )
        except LLMUnavailable as e:
            # A backend was configured but is unreachable - surface for triage.
            logger.warning("LLM backend unavailable, using heuristic: %s", e)
            return None
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM narration failed, using heuristic: %s", e)
            return None
        return self._sanitize_llm(text)

    @staticmethod
    def _sanitize_llm(text: Optional[str]) -> Optional[str]:
        """Treat model output as untrusted (standard 6.2): strip control
        characters, collapse whitespace, and cap length. The prompt only ever
        contains our own computed market facts - never credentials - so secret
        leakage is structurally impossible; this guard is defense-in-depth."""
        if not text:
            return None
        cleaned = "".join(
            ch if (ch in "\t\n\r " or ord(ch) >= 32) else " " for ch in text
        )
        cleaned = " ".join(cleaned.split())
        if not cleaned:
            return None
        return cleaned[:2000]

    async def respond(

        self, message: str, history: Optional[List[Dict[str, str]]] = None

    ) -> Dict[str, Any]:

        text = (message or "").strip()

        if not text:

            return {

                "reply": "Ask me about any market — e.g. \"Analyze XAUUSD\" or "

                "\"What's the BTC sentiment?\".",

                "suggestions": self.suggestions(),

                "context": {},

            }



        low = text.lower()



        # 1) Symbol detection (known catalog first, then any forex-style pair).

        symbol = self._detect_symbol(text)



        # 2) Intent routing.

        if any(k in low for k in ("help", "what can you", "how do you", "who are you")):

            return self._help(symbol)



        if any(k in low for k in ("risk", "drawdown", "volatility target", "position size rule")):

            return self._risk(symbol)



        if any(k in low for k in ("symbol", "market", "list", "avail", "trade", "what can i trade")):

            return self._symbols(symbol)



        if any(k in low for k in ("news", "headline", "latest")):

            return await self._news(symbol)



        # Symbol-specific read is the default when a symbol is recognized.

        if symbol:

            return await self._analyze_symbol(symbol, text)



        # Generic fallback: score the user's sentiment and give market mood.

        return await self._generic(text)



    # ------------------------------------------------------------------ #

    # Intents

    # ------------------------------------------------------------------ #

    def _help(self, symbol: Optional[str]) -> Dict[str, Any]:

        reply = (

            "I'm the Quant AI Terminal assistant. I can help you with:\n"

            "• **Market read** — \"Analyze BTCUSDT\" or \"XAUUSD outlook\"\n"

            "• **Sentiment** — \"What's the EURUSD sentiment?\"\n"

            "• **Risk settings** — \"Show risk settings\"\n"

            "• **Markets** — \"List available markets\"\n"

            "• **News** — \"Latest important news\"\n\n"

            "I use live ticks (when the feed is connected), FinBERT-scored news, "

            "and your configured risk rules. Everything works even offline — I just "

            "lean on the curated feed instead of a live one."

        )

        return {"reply": reply, "suggestions": self.suggestions(), "context": {"intent": "help"}}



    def _risk(self, symbol: Optional[str]) -> Dict[str, Any]:

        rows = [

            f"• Max drawdown: {settings.MAX_DRAWDOWN_PCT*100:.1f}%",

            f"• Target volatility: {settings.TARGET_VOLATILITY*100:.1f}%",

            f"• Risk per trade: {settings.RISK_PER_TRADE_PCT*100:.1f}%",

            f"• Min confidence to act: {settings.MIN_CONFIDENCE_THRESHOLD*100:.1f}%",

            f"• Circuit-breaker cooldown: {settings.CIRCUIT_BREAKER_COOLDOWN_HOURS}h",

        ]

        target = f" for {symbol}" if symbol else ""

        reply = "Current risk configuration" + target + ":\n" + "\n".join(rows)

        return {

            "reply": reply,

            "suggestions": self.suggestions(),

            "context": {"intent": "risk", "symbol": symbol},

        }



    def _symbols(self, symbol: Optional[str]) -> Dict[str, Any]:

        cat = settings.symbol_catalog()

        parts = [

            "**Available markets:**",

            "• Crypto: " + ", ".join(cat["crypto"]),

            "• Forex Majors: " + ", ".join(cat["forex_majors"]),

            "• Forex Minors: " + ", ".join(cat["forex_minors"]),

            "• Commodities: " + ", ".join(cat["commodities"]),

        ]

        note = (

            "\n\nNote: Binance streams crypto live only. Forex & commodities (e.g. "

            "XAUUSD) are supported for chart-image analysis and as selectable "

            "symbols; a dedicated feed is needed for live ticks."

        )

        return {

            "reply": "\n".join(parts) + note,

            "suggestions": self.suggestions(),

            "context": {"intent": "symbols"},

        }



    async def _news(self, symbol: Optional[str]) -> Dict[str, Any]:

        data = await news_service.get_latest(limit=5)

        items = data.get("items", [])

        if symbol:

            matched = [i for i in items if symbol in (i.get("symbols") or [])]

            if matched:

                items = matched

        if not items:

            return {

                "reply": "No important headlines right now.",

                "suggestions": self.suggestions(),

                "context": {"intent": "news", "symbol": symbol},

            }

        lines = []

        for i in items[:5]:

            s = i.get("sentiment", "neutral")

            lines.append(f"• [{s.upper()}] {i['title']}")

        src = data.get("source", "curated")

        reply = f"Latest important news (source: {src}):\n" + "\n".join(lines)

        return {

            "reply": reply,

            "suggestions": self.suggestions(),

            "context": {"intent": "news", "symbol": symbol},

        }



    async def _analyze_symbol(self, symbol: str, text: str) -> Dict[str, Any]:
        # Live price from Redis (optional).
        price = None
        r = get_redis()
        if r is not None:
            try:
                tick = await r.get(f"tick:latest:{symbol.upper()}")
                if tick:
                    import json
                    price = json.loads(tick).get("price")
            except Exception:  # noqa: BLE001
                price = None

        # News sentiment for this symbol.
        data = await news_service.get_latest(limit=50)
        sym_news = [i for i in data.get("items", []) if symbol in (i.get("symbols") or [])]
        if sym_news:
            scores = [i.get("sentiment_score", 0.5) for i in sym_news]
            avg = sum(scores) / len(scores)
            mood = "bullish" if avg > 0.56 else "bearish" if avg < 0.44 else "neutral"
            headlines = "; ".join(i["title"] for i in sym_news[:2])
            news_line = (
                f"News flow skews {mood} (avg score {avg:.2f}). Highlights: {headlines}."
            )
        else:
            news_line = "No symbol-specific headlines in the current feed."

        # Overall market mood (from all curated/live items).
        all_items = data.get("items", [])
        if all_items:
            overall = sum(i.get("sentiment_score", 0.5) for i in all_items) / len(all_items)
            overall_mood = (
                "risk-on" if overall > 0.54 else "risk-off" if overall < 0.46 else "balanced"
            )
        else:
            overall_mood = "balanced"

        # Market-strength read (ADX / composite), best-effort.
        strength_line = ""
        try:
            st = await market_strength_service.compute(symbol, "5m")
            strength_line = "Strength: %.0f/100 (%s, ADX %.0f). " % (
                st["strength"], st["bias"], st["adx"]
            )
        except Exception:  # noqa: BLE001
            strength_line = ""

        price_line = f" Last traded around {price}." if price is not None else ""
        # Deterministic facts only - the LLM (if configured) narrates these but
        # never invents numbers. Falls back to the templated text below.
        facts = (
            f"Symbol: {symbol}\n"
            f"Last price: {price if price is not None else 'unknown'}\n"
            f"News: {news_line}\n"
            f"Market strength: {strength_line.strip() if strength_line else 'n/a'}\n"
            f"Broader market mood: {overall_mood}\n"
            f"Risk rule: minimum confidence to act is "
            f"{settings.MIN_CONFIDENCE_THRESHOLD*100:.0f}%."
        )
        llm_reply = await self._maybe_llm(ANALYST_SYSTEM, facts)
        if llm_reply:
            reply = llm_reply
        else:
            reply = (
                f"**{symbol}** read:{price_line}\n{news_line}\n"
                f"{strength_line}"
                f"Broader tape looks {overall_mood}. "
                f"Use the chart + indicators above and respect the risk rules "
                f"(min confidence {settings.MIN_CONFIDENCE_THRESHOLD*100:.0f}%) before acting."
            )
        return {
            "reply": reply,
            "suggestions": self.suggestions(),
            "context": {"intent": "analyze", "symbol": symbol, "price": price},
        }

    async def _generic(self, text: str) -> Dict[str, Any]:

        # Score the user's own message for market mood.

        try:

            sc = sentiment_engine.analyze_sync([text])[0]

        except Exception:  # noqa: BLE001

            sc = {"label": "neutral", "score": 0.5}

        mood = sc.get("label", "neutral")

        data = await news_service.get_latest(limit=5)

        top = data.get("items", [])[0] if data.get("items") else None

        reply = (

            f"I read your note as **{mood}**. "

            f"The most important headline right now is: "

            f"\"{top['title'] if top else 'n/a'}\". "

            f"Ask me to \"Analyze <SYMBOL>\" for a market-specific read, or "

            f"\"List available markets\" to see what's tradable."

        )

        return {

            "reply": reply,

            "suggestions": self.suggestions(),

            "context": {"intent": "generic", "mood": mood},

        }



    # ------------------------------------------------------------------ #

    # Helpers

    # ------------------------------------------------------------------ #

    async def analyze_snapshot(
        self, image_b64: str, symbol: Optional[str]
    ) -> Dict[str, Any]:
        """Analyze a chart snapshot (base64 PNG) and return a chat-ready summary
        plus a trade plan (entry/SL/TP/forecast/patterns) when possible.

        The image goes through the OCR/pattern analyzer; if a symbol is known (or
        detected in the image) we additionally build a trade plan from candles.
        Fully graceful: missing image / no history still yields a useful reply.
        """
        raw = b""
        if image_b64:
            try:
                payload = image_b64.split(",", 1)[1] if "," in image_b64 else image_b64
                raw = base64.b64decode(payload)
            except Exception:  # noqa: BLE001
                raw = b""

        analysis = await chart_analyzer.analyze(raw) if raw else {
            "status": "empty",
            "notes": ["no image data"],
        }

        eff = symbol or analysis.get("symbol")
        plan = None
        if eff:
            try:
                plan = await trade_plan_service.build(eff, "5m")
            except DataUnavailable:
                plan = None
            except Exception as e:  # noqa: BLE001
                logger.debug("snapshot plan build failed: %s", e)
                plan = None

        reply = self._format_snapshot_reply(analysis, plan, eff)
        # Optional LLM commentary over the deterministic snapshot read.
        try:
            sym = eff or analysis.get("symbol") or "the chart"
            plan_summary = (
                f"Direction {plan['direction'].upper()}, entry {plan['entry']:.4f}, "
                f"SL {plan['stop_loss']:.4f}, TP {plan['take_profit']:.4f}, "
                f"RR {plan['risk_reward']:.1f}"
                if plan and plan.get("entry") is not None
                else "no tradable plan (insufficient history)"
            )
            comm = await self._maybe_llm(
                ANALYST_SYSTEM,
                f"Chart snapshot for {sym}. Detected patterns: "
                f"{', '.join(analysis.get('detected_patterns') or []) or 'none'}. "
                f"Chart sentiment: {analysis.get('sentiment') or 'unknown'}. "
                f"Trade plan: {plan_summary}. "
                f"Give a concise 2-3 sentence trading-read commentary. "
                f"Do not invent prices; use only the facts above.",
            )
            if comm:
                reply = reply + "\n\n" + comm.strip()
        except Exception:  # noqa: BLE001
            logger.debug("snapshot llm commentary skipped", exc_info=True)
        return {"reply": reply, "analysis": analysis, "plan": plan, "symbol": eff}

    def _format_snapshot_reply(
        self, analysis: Dict[str, Any], plan: Optional[Dict[str, Any]], symbol: Optional[str]
    ) -> str:
        sym = symbol or analysis.get("symbol") or "the chart"
        lines = [f"**Snapshot analysis — {sym}**"]

        patterns = analysis.get("detected_patterns") or []
        if patterns:
            lines.append(f"• Patterns (OCR): {', '.join(patterns)}")
        sentiment = analysis.get("sentiment")
        if sentiment:
            lines.append(f"• Chart sentiment: {sentiment} (conf {analysis.get('confidence', 0):.2f})")

        if plan:
            if plan.get("entry") is None:
                lines.append(
                    f"• No tradable plan: {plan.get('patterns', ['no history'])[0]}"
                )
            else:
                direction = plan["direction"].upper()
                lines.append(
                    f"• Plan: **{direction}** (signal {plan['signal']}, "
                    f"conf {plan['confidence']:.2f}, RR {plan['risk_reward']:.1f})"
                )
                lines.append(
                    f"• Entry {plan['entry']:.4f} | SL {plan['stop_loss']:.4f} | "
                    f"TP {plan['take_profit']:.4f}"
                )
                if plan.get("support"):
                    lines.append(
                        f"• Support ~{plan['support']:.4f} | Resistance ~{plan['resistance']:.4f}"
                    )
                if plan.get("forecast"):
                    lines.append("• Forecast line projected forward (dashed on chart).")
                pat = [p for p in plan.get("patterns", []) if "Support" not in p and "Resistance" not in p]
                if pat:
                    lines.append(f"• Formation: {', '.join(pat)}")
        else:
            lines.append(
                "• No live candle history for this symbol, so I can't draw a price "
                "plan — the snapshot patterns/sentiment above still apply."
            )

        lines.append(
            "Plan is drawn on the chart (entry/SL/TP + forecast). Not financial advice."
        )
        return chr(10).join(lines)

    def _detect_symbol(self, text: str) -> Optional[str]:

        upper = text.upper()

        cat = settings.symbol_catalog()

        known = set()

        for grp in cat.values():

            known.update(grp)

        # Exact known symbol (word boundary, allow BTCUSDT etc.).

        for sym in known:

            if re.search(rf"\b{sym}\b", upper):

                return sym

        # Generic forex/commodity pair e.g. EURUSD, XAUUSD.

        m = _PAIR_RE.search(upper)

        if m:

            cand = m.group(1) + m.group(2)

            # Avoid catching words like "THE" or "API" by requiring a plausible pair.

            if cand in known or cand in {

                "XAUUSD", "XAGUSD", "XAUEUR", "XAGEUR",

            } or (m.group(1) in {

                "EUR", "GBP", "USD", "JPY", "CHF", "AUD", "CAD", "NZD", "XAU", "XAG",

            } and m.group(2) in {

                "USD", "JPY", "EUR", "GBP", "CHF", "AUD", "CAD", "NZD", "XAU", "XAG",

            }):

                return cand

        return None





chat_assistant = ChatAssistant()
