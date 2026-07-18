"""Behavioral tests for app.core.auth + app.core.metrics (§2.2, §5.2)."""
from __future__ import annotations

import asyncio

import app.core.auth as auth
from app.core import metrics
from fastapi import HTTPException

from tests.helpers import FakeRequest, patch


def test_auth_disabled_allows_protected_route():
    with patch(auth.settings, "API_AUTH_ENABLED", False):
        asyncio.run(auth.require_api_key(FakeRequest("/api/v1/chat")))  # no raise


def test_auth_enabled_without_key_denies_503():
    with patch(auth.settings, "API_AUTH_ENABLED", True), patch(
        auth.settings, "API_KEY", ""
    ), patch(auth.settings, "API_KEYS", ""):
        raised = None
        try:
            asyncio.run(auth.require_api_key(FakeRequest("/api/v1/chat")))
        except HTTPException as e:
            raised = e
        assert raised is not None and raised.status_code == 503


def test_auth_missing_key_401():
    with patch(auth.settings, "API_AUTH_ENABLED", True), patch(
        auth.settings, "API_KEY", "secret"
    ), patch(auth.settings, "API_KEYS", ""):
        raised = None
        try:
            asyncio.run(auth.require_api_key(FakeRequest("/api/v1/chat")))
        except HTTPException as e:
            raised = e
        assert raised is not None and raised.status_code == 401


def test_auth_valid_key_ok():
    with patch(auth.settings, "API_AUTH_ENABLED", True), patch(
        auth.settings, "API_KEY", "secret"
    ), patch(auth.settings, "API_KEYS", ""):
        asyncio.run(
            auth.require_api_key(
                FakeRequest("/api/v1/chat", headers={"X-API-Key": "secret"})
            )
        )
        asyncio.run(
            auth.require_api_key(
                FakeRequest("/api/v1/chat", query={"api_key": "secret"})
            )
        )


def test_metrics_endpoint_path_is_public():
    with patch(auth.settings, "API_AUTH_ENABLED", True), patch(
        auth.settings, "API_KEY", "secret"
    ), patch(auth.settings, "API_KEYS", ""):
        asyncio.run(auth.require_api_key(FakeRequest("/metrics")))
        asyncio.run(auth.require_api_key(FakeRequest("/healthz")))
        asyncio.run(auth.require_api_key(FakeRequest("/docs")))


def test_auth_api_keys_list_allows_secondary():
    with patch(auth.settings, "API_AUTH_ENABLED", True), patch(
        auth.settings, "API_KEY", ""
    ), patch(auth.settings, "API_KEYS", "k1,k2"):
        asyncio.run(
            auth.require_api_key(
                FakeRequest("/api/v1/chat", headers={"X-API-Key": "k2"})
            )
        )
        raised = None
        try:
            asyncio.run(
                auth.require_api_key(
                    FakeRequest("/api/v1/chat", headers={"X-API-Key": "bad"})
                )
            )
        except HTTPException as e:
            raised = e
        assert raised is not None and raised.status_code == 401


def test_is_valid_key_constant_time_compare():
    with patch(auth.settings, "API_KEY", "abc"), patch(auth.settings, "API_KEYS", ""):
        assert auth.is_valid_key("abc") is True
        assert auth.is_valid_key("ABC") is False  # case-sensitive
        assert auth.is_valid_key(None) is False
        assert auth.is_valid_key("") is False


def test_metrics_text_format():
    metrics.reset()
    metrics.inc("rate_limit_denied", 3)
    metrics.record_request(0.1, 200, "GET")
    text = metrics.get_text()
    assert "quant_requests_total 1" in text
    assert "quant_rate_limit_denied 3" in text
    assert "# TYPE quant_rate_limit_denied counter" in text
    assert "# HELP quant_uptime_seconds" in text
