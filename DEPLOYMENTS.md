# Deployment Runbook — Quant AI Terminal

This is the operational deployment guide for the Quant AI Terminal: a **FastAPI
backend** (charts, chat, news, image analysis, AI engine, metrics, auth) plus a
**Next.js frontend**. It complements [`README.md`](./README.md) and the
[`ENGINEERING_STANDARD.md`](./ENGINEERING_STANDARD.md) compliance matrix.

> **TL;DR** — backend needs **Postgres/TimescaleDB + Redis**; frontend is a
> static Next.js build (Vercel or any static host). Copy
> [`.env.example`](./.env.example) to `.env`, fill in the secrets, run Alembic
> once, and start the web process (plus an optional `worker`).

---

## 1. Architecture

```
┌──────────────┐      HTTPS / WS      ┌──────────────────────────────┐
│  Next.js     │ ───────────────────▶ │  FastAPI (web process)        │
│  Frontend    │  X-API-Key (opt)     │  :8000  /api/v1/*  /metrics   │
│  (Vercel)    │                      │  /healthz /readyz /docs        │
└──────────────┘                      └───────┬───────────────┬────────┘
                                               │              │
                                         ┌─────▼─────┐  ┌─────▼─────┐
                                         │ TimescaleDB│  │   Redis   │
                                         │ (Postgres) │  │pub/sub+cache│
                                         └───────────┘  └───────────┘
                          (optional, separate process)
                     ┌─────────────────────────────────────────────┐
                     │  `python -m app.worker`  (ingest + learning)  │
                     └─────────────────────────────────────────────┘
```

- **Web process** serves HTTP + WebSocket and runs the supervised
  background tasks when `RUN_BACKGROUND_TASKS=true` (single instance) or
  delegates them to a dedicated `worker` for multi-replica setups.
- All heavy dependencies (TimescaleDB, Redis, model weights, FinBERT, LLM
  API) are **optional** — the app degrades gracefully (neutral/heuristic
  behavior, no crash) when any are unavailable.

---

## 2. Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | Backend runtime |
| Node 20+ | Frontend build (`npm run build`) |
| Postgres / **TimescaleDB** | `TIMESCALEDB_URL` (asyncpg) |
| Redis 7+ | `REDIS_URL` — pub/sub, cache, shared rate limiter |
| Model weights (optional) | TFT / LightGBM / scalers under `MODEL_DIR`; FinBERT auto-downloads if online |
| LLM API key (optional) | `LLM_CLOUD_API_KEY` for the cloud reasoning plane |
| Live-Rates key (optional) | `LIVERATES_API_KEY` for live forex/commodity ticks |

---

## 3. Environment variables

Copy `.env.example` → `.env` and adjust. **Never commit `.env`** (it is
gitignored). Key variables:

### Core
| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_ENV` | `production` | Env profile; warns if `localhost` stores are used in `production` |
| `APP_NAME` | `Quant AI Terminal` | Reported by `/healthz` |
| `LOG_LEVEL` | `INFO` | Backend log level |
| `FRONTEND_URL` | `http://localhost:3000` | CORS allow-origin |
| `RUN_BACKGROUND_TASKS` | `true` | Web process also runs ingest/learning (set `false` + run `app.worker` for replicas) |

### Data stores
| Variable | Purpose |
|----------|---------|
| `TIMESCALEDB_URL` | e.g. `postgresql+asyncpg://quant:pass@host:5432/forex` |
| `REDIS_URL` | e.g. `redis://host:6379/0` |

### Rate limiting (Standard §6.3)
| Variable | Default | Purpose |
|----------|---------|---------|
| `RATE_LIMIT_REDIS_ENABLED` | `true` | Shared Redis sliding-window; `false` → in-process only |

### API authentication (Standard §2.2)
| Variable | Default | Purpose |
|----------|---------|---------|
| `API_AUTH_ENABLED` | `false` | Enable `X-API-Key` enforcement on all routes except health/metrics/docs |
| `API_KEY` | _(empty)_ | Single accepted key (constant-time compare) |
| `API_KEYS` | _(empty)_ | Comma-separated additional keys |
| `API_KEY_HEADER` | `X-API-Key` | Header name; `?api_key=` query also accepted |

> **Fail-closed:** if auth is enabled but no key is configured, every request
> is denied with `503`. When enabled, set the frontend's `NEXT_PUBLIC_API_KEY`
> to the same value.

### LLM reasoning plane (§6)
| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_PROVIDER` | `hybrid` | `hybrid` (cloud→ollama→off) \| `cloud` \| `ollama` \| `off` |
| `LLM_CLOUD_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible endpoint |
| `LLM_CLOUD_API_KEY` | _(empty)_ | Required for `cloud`/`hybrid` cloud path |
| `LLM_CLOUD_MODEL` | `gpt-4o-mini` | Chat model |
| `LLM_OLLAMA_URL` | `http://localhost:11434` | Local Ollama |
| `LLM_OLLAMA_MODEL` | `llama3.1:8b` | Local model |
| `LLM_TIMEOUT` / `LLM_MAX_TOKENS` / `LLM_TEMPERATURE` | `30` / `600` / `0.3` | Completion params |

### Forex / commodities (§1, always analyzed; live ticks optional)
| Variable | Default | Purpose |
|----------|---------|---------|
| `ENABLE_FOREX` / `ENABLE_COMMODITIES` | `true` | Symbol catalogs |
| `FOREX_MAJORS` / `FOREX_MINORS` / `COMMODITIES` | EUR/USD… / XAUUSD | Catalog entries |
| `FOREX_SOURCE` | `live_rates` | `none` to disable live forex; `live_rates_ws` for socket.io |
| `LIVERATES_API_KEY` | _(empty)_ | Enable live forex/commodity ticks |

### News, models, image analysis
| Variable | Default | Purpose |
|----------|---------|---------|
| `NEWS_API_URL` / `NEWS_API_KEY` | _(empty)_ | Optional live news; curated offline set used if blank |
| `MODEL_DIR` / `TFT_MODEL_PATH` / `LGBM_MODEL_PATH` / `SCALER_PATH` | `/opt/...` | Optional model files |
| `FINBERT_MODEL` | `ProsusAI/finbert` | Sentiment model (downloaded if online) |
| `MAX_UPLOAD_SIZE_MB` | `10` | Server-side chart-image upload cap |
| `TESSERACT_CMD` | `/usr/bin/tesseract` | OCR binary for image analysis |

### Frontend (inlined at **build time** — must be set before `npm run build`)
| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_URL` | Backend base URL, e.g. `https://api.your-domain.com` |
| `NEXT_PUBLIC_WS_URL` | Backend WS URL, e.g. `wss://api.your-domain.com` |
| `NEXT_PUBLIC_API_KEY` | Same value as backend `API_KEY` when auth is enabled |

---

## 4. Backend deployment

The root **`Dockerfile`** builds the image and runs
`uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1`.

### 4.1 Local full stack (Docker Compose)
```bash
cp .env.example .env            # edit secrets
docker compose up --build
docker compose run --rm web alembic upgrade head   # create schema (once)
# app on :8000, frontend on :3000, TimescaleDB on :5432, Redis on :6379
```
The compose file splits the web process (`RUN_BACKGROUND_TASKS=false`) from a
dedicated `worker` (`python -m app.worker`) for clean separation, and includes a
production multi-stage Next.js frontend image.

### 4.2 Railway
- Import the repo; the root **`railway.toml`** builds via the Dockerfile.
- Healthcheck: `GET /healthz` (see `healthcheckPath`).
- Set env vars in the Railway project: `TIMESCALEDB_URL`, `REDIS_URL`,
  `LLM_CLOUD_API_KEY`, `FRONTEND_URL`, `API_AUTH_ENABLED`, `API_KEY`, …
- One service runs the web process. For multiple replicas, run
  `python -m app.worker` separately and set `RUN_BACKGROUND_TASKS=false` on web.

### 4.3 Fly.io
- `fly.toml` targets region **`lhr`** (London, close to KE), health-checks
  `/healthz`, and runs background tasks in-process (`RUN_BACKGROUND_TASKS=true`)
  for a single instance.
```bash
fly launch
fly secrets set REDIS_URL=... TIMESCALEDB_URL=... LLM_CLOUD_API_KEY=... \
  FRONTEND_URL=https://your-app.vercel.app API_AUTH_ENABLED=true API_KEY=...
fly deploy
```

### 4.4 Manual / multi-replica
```bash
pip install -r requirements.txt
alembic upgrade head                      # schema
# web (serves traffic + WS):
RUN_BACKGROUND_TASKS=false uvicorn app.main:app --host 0.0.0.0 --port 8000
# separate worker (ingest + learning) on each extra host:
RUN_BACKGROUND_TASKS=true python -m app.worker
```

---

## 5. Frontend deployment (Vercel)

`frontend/vercel.json` pins `framework: nextjs`, `buildCommand: npm run build`.
`next.config.js` uses `output: 'standalone'`.

1. Import the **`frontend/`** folder as a Vercel project.
2. Set **build env vars** (inlined at build time):
   - `NEXT_PUBLIC_API_URL` → your backend URL (e.g. `https://api.your-domain.com`)
   - `NEXT_PUBLIC_WS_URL` → `wss://api.your-domain.com`
   - `NEXT_PUBLIC_API_KEY` → same as backend `API_KEY` if auth is enabled
3. Deploy. The app falls back to `http://localhost:8000` for local dev.

> Any static host works — just build `frontend/` with the `NEXT_PUBLIC_*`
> vars set and serve the `.next` output (e.g. via the included
> `frontend/Dockerfile` in compose).

---

## 6. Database schema (Alembic)

Migrations live in `alembic/`. Apply once (and on upgrade):
```bash
docker compose run --rm web alembic upgrade head      # or: alembic upgrade head
```
Migrations are backward-compatible / coordinated, satisfying §7.2.

---

## 7. Enabling production-grade features

| Feature | Standard | How to enable |
|---------|----------|---------------|
| API key auth | §2.2 | `API_AUTH_ENABLED=true` + `API_KEY` (or `API_KEYS`); set frontend `NEXT_PUBLIC_API_KEY` |
| Prometheus metrics | §5.2 | `GET /metrics` (auth-exempt); scrape from Grafana/Prometheus |
| Structured JSON logging | §5.1 | Default in `app/main.py`; `LOG_LEVEL` controls verbosity; secrets redacted |
| Hybrid LLM narration | §6 | `LLM_PROVIDER=hybrid` + `LLM_CLOUD_API_KEY` (or `ollama`) |
| Live forex/commodity feed | §1 | `FOREX_SOURCE=live_rates` + `LIVERATES_API_KEY` |
| Shared rate limiter | §6.3 | `RATE_LIMIT_REDIS_ENABLED=true` (default) |

---

## 8. Health, readiness & observability

- **Liveness** `GET /healthz` — process alive, no dependencies needed (cheap).
- **Readiness** `GET /readyz` (alias `/health`) — pings Redis + DB (3s bounded
  timeout) and reports per-dependency status; returns `503` if not ready so the
  orchestrator stops routing.
- **Metrics** `GET /metrics` — request count, latency, error rate, rate-limit
  denials, LLM/WebSocket counters (Prometheus format).
- Structured JSON logs (§5.1) make triage straightforward in any aggregator.
- Alert on `/readyz` flipping to `503` and on `quant_request_errors_total`
  / `quant_rate_limit_denied` spikes.

---

## 9. CI/CD

[`.github/workflows/ci.yml`](./.github/workflows/ci.yml) runs on push/PR to
`main`:
- `python -m compileall -q app`
- `pytest` (Python 3.11 + 3.13) — `tests/` suite with graceful stubbing
- best-effort frontend type-check/build

The suite exercises `ratelimit`, `llm`, and `auth`/`metrics` behavioral paths;
it only stubs heavy deps when they are absent, so CI runs the real code.

---

## 10. Rollback & notes

- Containers are immutable images; rollback = redeploy previous image/tag.
- DB changes go through Alembic (reversible migrations preferred).
- Observability (metrics + structured logs + health) ships with every deploy,
  satisfying §7.2 (deployment readiness) and §7.3 (no silent handling).
