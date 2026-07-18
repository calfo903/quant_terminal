# Quant AI Terminal

AI-driven quantitative trading terminal: a FastAPI backend + Next.js (TypeScript)
frontend for crypto / forex / commodity charting, image-chart analysis, a FinBERT-
scored news feed, and a data-aware AI chat assistant.

## Stack

- **Backend**: FastAPI, SQLAlchemy+asyncpg (TimescaleDB), Redis (pub/sub + cache),
  FinBERT (transformers), LightGBM / PyTorch (optional models), OpenCV + Tesseract
  (optional image analysis). Everything degrades gracefully when models, DB, Redis
  or the network are unavailable.
- **Frontend**: Next.js 14, React 18, lightweight-charts, Tailwind CSS.

## Features

- **Charts tool** (`frontend/components/ChartToolbar.tsx` + `TradingViewChart.tsx`)
  - Symbol search + grouped dropdown (crypto / forex majors / forex minors /
    commodities) driven by `GET /api/v1/charts/symbols`.
  - Timeframe selector (1m–1d), chart types (Candles / Bars / Line / Area).
  - Toggleable indicators: **MA** (SMA 20/50), **EMA** (20), **RSI** (14, sub-pane
    with 30/70 bands), and **Volume** overlay — served by
    `GET /api/v1/charts/{instrument}/indicators`.
  - Live ticks stream over WebSocket (`/api/v1/ws/chart/{instrument}`).
- **Latest important news sidebar** (`frontend/components/NewsSidebar.tsx`)
  - `GET /api/v1/news?limit=&category=` returns FinBERT-scored headlines ranked by
    importance, auto-refreshing every 60s. Degrades to a curated offline set
    (`NEWS_API_URL` is optional). Clicking a symbol chip loads it on the chart.
- **AI chat panel** (`frontend/components/ChatPanel.tsx`)
  - `POST /api/v1/chat` + `GET /api/v1/chat/suggestions`. Data-aware assistant that
    detects symbols, reports live price (if the feed is connected), summarizes news
    sentiment, and lists risk settings. No external LLM required — fully offline.
- **XAUUSD (Gold)** added as a commodity (`COMMODITIES=XAUUSD` in config / `.env`).
  Selectable on the chart, classified in image analysis (`market=commodity`), and
  featured in the news feed.
- **Trade plan overlay** (`POST /api/v1/charts/{instrument}/plan` +
  `app/services/ai_engine/trade_plan.py`). Computes **entry**, **stop-loss**,
  **take-profit** (ATR-based), a **predictive/forecast line**, and **pattern
  formation** detection (trend HH/HL, support/resistance, double top/bottom).
  Drawn on the chart (Entry/SL/TP + forecast dashed line) and summarized in chat.
  The **⚡ Analyze** toolbar button runs it; the **AI chat explains it**.
- **Snapshot & Analyze** (chat panel → `POST /api/v1/chat/snapshot`).
  Captures the live chart canvas, OCR/pattern-analyzes it, builds a trade plan
  when a symbol is known, and draws it on the chart — all from the chat panel.
- **Fullscreen chart** — toolbar toggle expands the chart to a full-viewport overlay
  (auto-resized via `ResizeObserver`).
- **Live forex / commodity feed** (pluggable `MarketSource` interface,
  `app/services/data_ingestion/market_source.py`). Two Live-Rates adapters ship:
  `LiveRatesSource` (REST polling, default) and `LiveRatesWsSource`
  (WebSocket/socket.io, true sub-second — `pip install 'python-socketio[client]'`
  + `FOREX_SOURCE=live_rates_ws`). Both publish normalized ticks into the same
  Redis pipeline Binance uses, so forex/commodity symbols get live price, WS
  updates, and trade plans. Enable with `FOREX_SOURCE=live_rates` +
  `LIVERATES_API_KEY` (see `.env`).
- **Persistent forex candles** — every non-crypto tick is aggregated into a
  rolling 1-minute candle store in Redis (`candle:1m:{symbol}`, capped at
  ~2 days). The historical fetcher prefers this store, so forex/XAUUSD charts,
  indicators, RSI and trade-plan overlays work and **survive restarts** without
  a separate history API.
- **Market Strength Indicators** — `GET /api/v1/charts/{instrument}/strength`
  (`app/services/ai_engine/market_strength.py`) returns ADX, RSI, MACD,
  Bollinger %B, ATR%, volume ratio, plus a composite 0–100 strength score and
  bias. The toolbar **Str** toggle draws an ADX + strength sub-pane, and a
  compact strip under the chart shows the metrics. The chat assistant also
  reports strength when you ask about a symbol.
- **Market Sessions** — `GET /api/v1/sessions` (`app/services/ai_engine/
  market_sessions.py`) returns the active forex session(s) in UTC (Sydney /
  Tokyo / London / New York). A ribbon under the chart highlights the open
  session(s) and current UTC time.
- **Feed status** — `GET /api/v1/status` reports which market sources
  (binance / live_rates) are currently streaming (inferred from Redis tick
  recency). The header shows a live/stale/idle dot per source, and the chart
  toolbar shows a per-symbol live-feed indicator.
- **Tick-built candles** — `HistoricalDataFetcher` falls back to building OHLCV
  from accumulated Redis tick history, so forex/commodity charts, indicators,
  RSI and the trade-plan/forecast overlays work without a separate history API.
- **Image-chart analysis** (OCR + pattern heuristics, optional FinBERT).

## Important caveats

- **Binance streams crypto only.** Live ticks exist for `BTCUSDT/ETHUSDT/SOLUSDT/
  XRPUSDT`. Forex pairs and **XAUUSD** are supported for chart-image analysis and as
  selectable symbols, but they have **no live tick feed** unless you wire in a
  dedicated market source. Their charts/news still render (gracefully empty offline).
- **Models are optional.** Missing TFT/LightGBM/FinBERT weights degrade to neutral /
  heuristic behavior instead of crashing.
- **Rate limiter is Redis-backed** (`app/core/ratelimit.py`). The chat / news /
  predict / analyze endpoints use a shared Redis sliding-window (atomic Lua
  `ZREMRANGEBYSCORE`/`ZCARD`/`ZADD`/`EXPIRE`) so **multiple uvicorn workers**
  enforce one global cap. If Redis is down or `RATE_LIMIT_REDIS_ENABLED=false`,
  it degrades to an in-process limiter (with a 30s dead-detection cooldown to
  avoid log spam) so the app never crashes. Limits (per client IP, honoring
  `X-Forwarded-For`): predict 10/min, analyze 5/min, chat 20/min, news 30/min.
- Run DB migrations with Alembic: `docker compose run --rm web alembic upgrade head`.

## Deployment (Vercel + Railway/Fly)

> Full, copy-paste deployment runbook (env-var reference, Railway / Fly.io /
> Vercel, Alembic, health checks, CI, rollback): see
> [DEPLOYMENTS.md](./DEPLOYMENTS.md).

The terminal is split into a **Next.js frontend** and a **FastAPI backend**
(which also runs the ingest worker, TimescaleDB, and Redis).

### Frontend → Vercel
- Import the `frontend/` folder as a Vercel project (or set it up manually).
- Set the build env var **`NEXT_PUBLIC_API_URL`** to your backend URL
  (e.g. `https://quant-api.up.railway.app` or `https://quant.fly.dev`). The app
  falls back to `http://localhost:8000` for local dev. `vercel.json` pins the
  framework/build; `next.config.js` already uses `output: 'standalone'`.

### Backend → Railway or Fly.io
- **Railway:** the root `Dockerfile` builds the image; `railway.toml` sets the
  healthcheck to `GET /healthz`. Add env vars from `.env.example` in the Railway
  project settings.
- **Fly.io:** `fly.toml` is provided (London region by default, close to KE).
  Run `fly launch` then `fly secrets set REDIS_URL=... TIMESCALEDB_URL=...
  LLM_CLOUD_API_KEY=...`. The container is health-checked on `/healthz`.
- Set **`FRONTEND_URL`** to your Vercel origin so CORS allows it.
- For a single instance keep `RUN_BACKGROUND_TASKS=true` (default) so the process
  also runs the Binance ingest + forex stream. For multiple replicas, set it
  `false` and run `python -m app.worker` separately.
- **API authentication** (standard 2.2): set `API_AUTH_ENABLED=true` + `API_KEY`
  (or `API_KEYS`) in production, and set the frontend's `NEXT_PUBLIC_API_KEY` to
  the same value. All routes except `/healthz`, `/readyz`, `/metrics`, and
  `/docs` then require the `X-API-Key` header (the WebSocket upgrade is checked
  too). Fail-closed if enabled without a key. Disabled by default for local/dev.
- **Metrics** (standard 5.2): `GET /metrics` exposes Prometheus-format request
  count, latency, error rate, rate-limit denials, and LLM/WebSocket counters —
  scrape it from your monitoring stack (Grafana/Prometheus).

### Hybrid LLM reasoning plane
The chat/analysis "reasoning" is produced by an LLM that consumes the
**deterministic signals** (ATR trade plan, FinBERT sentiment, strength) and writes
natural-language commentary. It never computes the trade numbers.
- `LLM_PROVIDER=hybrid` (default): tries the cloud API, then local **Ollama**,
  then falls back to the offline heuristic — no crash in any case.
- Cloud: any OpenAI-compatible endpoint (OpenAI `gpt-4o-mini`, DeepSeek, Groq,
  Together). Set `LLM_CLOUD_BASE_URL` / `LLM_CLOUD_API_KEY` / `LLM_CLOUD_MODEL`.
- Local: `ollama pull llama3.1:8b` and set `LLM_OLLAMA_URL`. Private, no token cost.
- `LLM_PROVIDER=off` keeps the assistant 100% offline (templated replies only).

## Testing & Quality

- **Behavioral `pytest` suite** lives in `tests/` (`test_ratelimit`, `test_llm`,
  `test_auth_metrics`). It exercises the real modules (`ratelimit`, `llm`,
  `auth`, `metrics`, `config`) with **stubbed boundaries** so it runs both in a
  minimal sandbox *and* in CI against the genuine dependencies:
  - `conftest.py` only injects lightweight stubs (fastapi / pydantic /
    pydantic-settings / httpx) when the real package is **not** importable, so
    CI always exercises real code.
  - LLM tests use a fake `httpx` module (no network); rate-limit tests use a
    fake Redis / in-memory fallback.
- **CI** (`.github/workflows/ci.yml`): on push/PR to `main`, runs
  `python -m compileall -q app` then `pytest` on Python 3.11 + 3.13, and a
  best-effort frontend type-check/build.
- **Structured JSON logging** (standard 5.1): `app/core/logging.py` emits
  single-line JSON via `JsonFormatter` and redacts secrets (by key and by value,
  e.g. API key / DB DSN / Redis URL). Wired into `app/main.py`; use
  `from app.core.logging import get_logger` instead of `logging.getLogger`.

## Layout

```
app/
  api/v1/{charts,websockets,image_analysis,analytics,news,chat}.py
  core/{config,database,scheduler,models,ratelimit}.py
  services/
    ai_engine/{model_registry,predictor,chat}.py
    data_ingestion/{binance_stream,historical}.py
    mlops/{sentiment,news}.py
    image_analysis/analyzer.py
    learning/tracker.py
    risk/manager.py
frontend/
  app/page.tsx                 # dashboard: charts tool + news sidebar + chat panel
  components/{TradingViewChart,ChartToolbar,NewsSidebar,ChatPanel,ImageUpload,AnalysisResults}.tsx
```

## License

Licensed under the **Apache License 2.0** — see [LICENSE](./LICENSE).
```
