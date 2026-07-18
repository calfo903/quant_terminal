"""Operational metrics endpoint (standard 5.2).

Prometheus-compatible text at GET /metrics. Auth-exempt (see
auth._PUBLIC_PATHS) so monitoring can scrape it without a key.
"""
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core import metrics

router = APIRouter()


@router.get("/metrics")
async def metrics_endpoint() -> PlainTextResponse:
    return PlainTextResponse(
        metrics.get_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
