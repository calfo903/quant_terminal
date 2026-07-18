"""API-key authentication at the transport boundary (standard 2.2).

A single global FastAPI dependency (`require_api_key`) enforces an
``X-API-Key`` header (or ``?api_key=`` query param) on every HTTP route except
a small allow-list of monitoring/documentation paths. WebSocket upgrades are
checked separately in ``app/api/v1/websockets.py`` (HTTP dependencies do not
run on WS connections) so there is no unauthenticated alternate path.

Key comparison uses ``hmac.compare_digest`` (constant-time) to avoid timing
leaks. The mechanism fails closed: if auth is enabled but no key is configured
the dependency denies everything with 503.
"""
import hmac
from typing import List, Optional

from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Routes that must stay open even when auth is on (monitoring + docs).
_PUBLIC_PATHS = {
    "/",
    "/healthz",
    "/readyz",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
}


def _valid_keys() -> List[str]:
    keys: List[str] = []
    if settings.API_KEY:
        keys.append(settings.API_KEY)
    if settings.API_KEYS:
        keys.extend(k.strip() for k in settings.API_KEYS.split(",") if k.strip())
    return keys


def is_valid_key(provided: Optional[str]) -> bool:
    if not provided:
        return False
    return any(hmac.compare_digest(provided, k) for k in _valid_keys())


async def require_api_key(request: Request) -> None:
    """Enforce API key on protected routes. Returns normally if allowed."""
    if not settings.API_AUTH_ENABLED:
        return
    if request.url.path in _PUBLIC_PATHS:
        return
    provided = request.headers.get(settings.API_KEY_HEADER) or request.query_params.get("api_key")
    if not _valid_keys():
        logger.error("API_AUTH_ENABLED=true but no API_KEY set; denying all requests")
        raise HTTPException(status_code=503, detail="Authentication misconfigured")
    if not is_valid_key(provided):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
