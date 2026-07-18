"""Behavioral tests for app.core.ratelimit (Engineering Standard §3.3, §6.3)."""
from __future__ import annotations

import asyncio

import app.core.ratelimit as rl
from fastapi import HTTPException

from tests.helpers import FakeRequest


def test_mem_limiter_allows_up_to_limit():
    lim = rl._MemLimiter(times=3, seconds=60)
    assert all(lim.is_allowed("k") for _ in range(3)) is True
    assert lim.is_allowed("k") is False  # 4th blocked


def test_mem_limiter_key_isolation():
    lim = rl._MemLimiter(times=1, seconds=60)
    assert lim.is_allowed("a") is True
    assert lim.is_allowed("a") is False
    assert lim.is_allowed("b") is True


def test_ratelimiter_in_memory_fallback():
    # enabled=False forces the in-process limiter (no redis getter consulted)
    lim = rl.RateLimiter("predict", times=2, seconds=60, enabled=False)
    assert asyncio.run(_allow_n(lim, "ip1", 2)) is True
    assert asyncio.run(lim.is_allowed("ip1")) is False


async def _allow_n(lim, key, n):
    for _ in range(n):
        if not await lim.is_allowed(key):
            return False
    return True


def test_ratelimiter_redis_getter_none_falls_back():
    lim = rl.RateLimiter(
        "analyze", times=1, seconds=60, enabled=True, redis_getter=lambda: None
    )
    assert asyncio.run(lim.is_allowed("ip2")) is True
    assert asyncio.run(lim.is_allowed("ip2")) is False


def test_ratelimiter_redis_success_path():
    class FakeRedis:
        async def eval(self, script, numkeys, key, *args):
            return 1  # always admit

    lim = rl.RateLimiter(
        "chat", times=5, seconds=60, enabled=True, redis_getter=lambda: FakeRedis()
    )
    assert asyncio.run(lim.is_allowed("ip3")) is True


def test_ratelimiter_redis_failure_falls_back():
    class BoomRedis:
        async def eval(self, *a, **k):
            raise RuntimeError("redis down")

    lim = rl.RateLimiter(
        "news", times=1, seconds=60, enabled=True, redis_getter=lambda: BoomRedis()
    )
    # first call: redis fails -> in-memory fallback admits
    assert asyncio.run(lim.is_allowed("ip4")) is True
    # subsequent call within window denied by the in-memory limiter
    assert asyncio.run(lim.is_allowed("ip4")) is False


def test_client_ip_x_forwarded_for():
    req = FakeRequest("/chat", headers={"x-forwarded-for": "9.9.9.9, 10.0.0.1"})
    assert rl._client_ip(req) == "9.9.9.9"


def test_client_ip_direct():
    req = FakeRequest("/chat", client_host="5.5.5.5")
    assert rl._client_ip(req) == "5.5.5.5"


def test_limit_dependency_raises_429():
    orig = rl._predict_limiter
    rl._predict_limiter = rl.RateLimiter("predict", times=0, seconds=60, enabled=False)
    try:
        req = FakeRequest("/predict")
        raised = None
        try:
            asyncio.run(rl.limit_predict(req))
        except HTTPException as e:
            raised = e
        assert raised is not None and raised.status_code == 429
    finally:
        rl._predict_limiter = orig
