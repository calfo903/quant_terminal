import logging

from pydantic_settings import BaseSettings

from pydantic import model_validator

import os





class Settings(BaseSettings):

    APP_NAME: str = "Quant AI Terminal"

    APP_ENV: str = os.getenv("APP_ENV", "production")

    DEBUG: bool = False

    LOG_LEVEL: str = "INFO"



    # Database

    TIMESCALEDB_URL: str = os.getenv("TIMESCALEDB_URL", "postgresql+asyncpg://quant:quant_password_2024@localhost:5432/forex")

    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Rate limiting: when True (default) the chat/news/predict/analyze
    # limiters use a shared Redis sliding-window so multiple uvicorn workers
    # enforce a single global cap. When False (or if Redis is unreachable),
    # they degrade to an in-process limiter. See app/core/ratelimit.py.
    RATE_LIMIT_REDIS_ENABLED: bool = True



    # Binance (Kenya-accessible)

    BINANCE_WS_URL: str = "wss://stream.binance.com:9443/ws"

    BINANCE_SYMBOLS: str = "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT"



    # Forex market - always enabled for analysis (majors + minors).

    # NOTE: Binance streams crypto only; forex pairs are supported for

    # chart-image analysis and as selectable symbols. Live forex ticks

    # would require a dedicated forex feed.

    ENABLE_FOREX: bool = True

    FOREX_MAJORS: str = "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,USDCAD,NZDUSD"

    FOREX_MINORS: str = "EURGBP,EURJPY,GBPJPY,AUDJPY,EURNZD,GBPCAD,AUDCAD,CHFJPY"

    # Commodities (always-enabled, e.g. XAUUSD = Gold spot vs US Dollar).
    ENABLE_COMMODITIES: bool = True
    COMMODITIES: str = "XAUUSD"



    def forex_symbols(self) -> list:

        if not self.ENABLE_FOREX:

            return []

        return [

            s.strip().upper()

            for s in (self.FOREX_MAJORS + "," + self.FOREX_MINORS).split(",")

            if s.strip()

        ]





    def commodity_symbols(self) -> list:
        if not self.ENABLE_COMMODITIES:
            return []
        return [s.strip().upper() for s in self.COMMODITIES.split(",") if s.strip()]

    def crypto_symbols(self) -> list:
        return [s.strip().upper() for s in self.BINANCE_SYMBOLS.split(",") if s.strip()]

    def symbol_catalog(self) -> dict:
        """Full tradeable-symbol catalog used by the chart toolbar / UI."""
        majors = {x.strip().upper() for x in self.FOREX_MAJORS.split(",") if x.strip()}
        minors = {x.strip().upper() for x in self.FOREX_MINORS.split(",") if x.strip()}
        return {
            "crypto": self.crypto_symbols(),
            "forex_majors": [s for s in self.forex_symbols() if s in majors],
            "forex_minors": [s for s in self.forex_symbols() if s in minors],
            "commodities": self.commodity_symbols(),
        }

    # ------------------------------------------------------------------ #
    # News (latest important headlines, FinBERT-scored)
    # ------------------------------------------------------------------ #
    NEWS_API_URL: str = os.getenv("NEWS_API_URL", "")
    NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", "")
    NEWS_CACHE_TTL: int = 900  # 15 min

    # ------------------------------------------------------------------ #
    # Chat assistant
    # ------------------------------------------------------------------ #
    CHAT_ENABLED: bool = True

    # ------------------------------------------------------------------ #
    # LLM reasoning plane (hybrid: cloud API + local Ollama, with a
    # deterministic-signal fallback). All keys are optional; with none set the
    # assistant stays fully offline (heuristic replies only). The LLM only
    # narrates the signals (price / strength / FinBERT / ATR plan) - it never
    # computes the trade numbers.
    # ------------------------------------------------------------------ #
    # Provider: "hybrid" (cloud -> ollama -> off) | "cloud" | "ollama" | "off"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "hybrid")
    # Cloud (OpenAI-compatible: OpenAI, DeepSeek, Groq, Together, ...)
    LLM_CLOUD_BASE_URL: str = os.getenv("LLM_CLOUD_BASE_URL", "https://api.openai.com/v1")
    LLM_CLOUD_API_KEY: str = os.getenv("LLM_CLOUD_API_KEY", "")
    LLM_CLOUD_MODEL: str = os.getenv("LLM_CLOUD_MODEL", "gpt-4o-mini")
    # Local Ollama (https://ollama.com) - private, no token cost.
    LLM_OLLAMA_URL: str = os.getenv("LLM_OLLAMA_URL", "http://localhost:11434")
    LLM_OLLAMA_MODEL: str = os.getenv("LLM_OLLAMA_MODEL", "llama3.1:8b")
    # Shared completion params.
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "30"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "600"))
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))

    # ------------------------------------------------------------------ #
    # API authentication (standard 2.2). When enabled, all routes except
    # health/metrics/docs require a valid X-API-Key header. The frontend sends
    # NEXT_PUBLIC_API_KEY. Disabled by default so local/dev stays open; set
    # API_AUTH_ENABLED=true + API_KEY for production.
    # ------------------------------------------------------------------ #
    API_AUTH_ENABLED: bool = (os.getenv("API_AUTH_ENABLED", "false").lower() in ("1", "true", "yes", "on"))
    API_KEY: str = os.getenv("API_KEY", "")
    API_KEYS: str = os.getenv("API_KEYS", "")  # comma-separated alternative
    API_KEY_HEADER: str = os.getenv("API_KEY_HEADER", "X-API-Key")

    # ------------------------------------------------------------------ #
    # Live forex / commodity market source (pluggable MarketSource)
    # ------------------------------------------------------------------ #
    # Set to "none" to disable live forex/commodity ticks (chart-image
    # analysis still works offline). "live_rates" uses Live-Rates free REST
    # polling (https://www.live-rates.com) which includes XAUUSD and needs
    # no credit card. Get a free key and set LIVERATES_API_KEY to enable.
    FOREX_SOURCE: str = os.getenv("FOREX_SOURCE", "live_rates")
    LIVERATES_API_KEY: str = os.getenv("LIVERATES_API_KEY", "")
    LIVERATES_POLL_INTERVAL: float = float(os.getenv("LIVERATES_POLL_INTERVAL", "2.0"))

    # MetaApi (optional)

    META_API_TOKEN: str = os.getenv("META_API_TOKEN", "")

    META_API_ACCOUNT_ID: str = os.getenv("META_API_ACCOUNT_ID", "")



    # AI Models

    MODEL_DIR: str = os.getenv("MODEL_DIR", "/opt/quant-terminal/backend/models")

    TFT_MODEL_PATH: str = os.getenv("TFT_MODEL_PATH", "/opt/quant-terminal/backend/models/tft_v3.pt")

    LGBM_MODEL_PATH: str = os.getenv("LGBM_MODEL_PATH", "/opt/quant-terminal/backend/models/lgbm_features.pkl")

    SCALER_PATH: str = os.getenv("SCALER_PATH", "/opt/quant-terminal/backend/models/scalers.pkl")

    DEVICE: str = "cpu"  # ARM64 CPU-only



    # FinBERT

    FINBERT_MODEL: str = os.getenv("FINBERT_MODEL", "ProsusAI/finbert")

    FINBERT_DEVICE: str = "cpu"



    # Risk Management

    MAX_DRAWDOWN_PCT: float = 0.05

    TARGET_VOLATILITY: float = 0.10

    RISK_PER_TRADE_PCT: float = 0.01

    MIN_CONFIDENCE_THRESHOLD: float = 0.65

    CIRCUIT_BREAKER_COOLDOWN_HOURS: int = 24



    # Image Analysis

    MAX_UPLOAD_SIZE_MB: int = 10

    TESSERACT_CMD: str = "/usr/bin/tesseract"



    # CORS

    FRONTEND_URL: str = "http://localhost:3000"



    # Background tasks: when True the web process ALSO runs the Binance ingest

    # stream + learning loop. In production set False and run `python -m app.worker`.

    RUN_BACKGROUND_TASKS: bool = True



    @model_validator(mode="after")

    def _validate_prod(self):

        if self.APP_ENV == "production":

            if "localhost" in self.REDIS_URL or "localhost" in self.TIMESCALEDB_URL:

                logging.warning(

                    "PRODUCTION configuration uses localhost data stores "

                    "(REDIS_URL / TIMESCALEDB_URL) - override for real deployments"

                )

        return self



    class Config:

        # Try both locations so it loads whether launched from the repo root

        # (where `.env` lives) or from a `backend/` directory.

        env_file = [".env", "backend/.env"]

        case_sensitive = True





settings = Settings()
