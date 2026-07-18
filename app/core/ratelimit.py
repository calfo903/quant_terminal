import time

from fastapi import HTTPException, Request
from app.core.logging import get_logger

try:  # redis is a hard dependency of the app (see app/core/database.py)
    from redis.exceptions import RedisError
except Exception:  # pragma: no cover - only if redis package is absent
    class RedisError(Exception):
        pass


logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# In-memory sliding-window limiter (single-process fallback)
# --------------------------------------------------------------------------- #
class _MemLimiter:
    """Sliding-window limiter keyed in-process. Uses monotonic time."""

    def __init__(self, times: int, seconds: int):
        self.times = times
        self.seconds = seconds
        self._buckets: dict = {}

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        dq = self._buckets.setdefault(key, [])
        cutoff = now - self.seconds
        while dq and dq[0] <= cutoff:
            dq.pop(0)
        if len(dq) >= self.times:
            return False
        dq.append(now)
        return True


# --------------------------------------------------------------------------- #
# Redis-backed sliding-window limiter (shared across workers)
# --------------------------------------------------------------------------- #
# Atomic check-and-add: prune entries older than the window, count the rest,
# and only admit the request if we are still under the limit. Using a Lua
# script guarantees the prune/count/add happens atomically across workers.
_SLIDE_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= max then
  return 0
end
redis.call('ZADD', key, now, now)
redis.call('EXPIRE', key, window + 1)
return 1
"""

# After a Redis failure we stop hammering Redis for this many seconds and
# silently use the in-memory limiter instead. Avoids log spam + tail latency.
_REDIS_DEAD_COOLDOWN_S = 30.0


class RateLimiter:
    """Sliding-window rate limiter.

    Primary backend is Redis (shared across uvicorn workers / instances).
    If Redis is unreachable or disabled, it degrades gracefully to an
    in-process limiter so the app keeps serving (just not globally capped).
    """

    def __init__(self, name: str, times: int, seconds: int,
                 enabled: bool = True, redis_getter=None):
        self.name = name
        self.times = times
        self.seconds = seconds
        self.enabled = enabled  # master switch (False => always in-memory)
        self._redis_getter = redis_getter or _default_redis_getter
        self._mem = _MemLimiter(times, seconds)
        self._redis_dead_until = 0.0  # monotonic timestamp

    async def is_allowed(self, key: str) -> bool:
        if not self.enabled:
            return self._mem.is_allowed(key)

        now_mono = time.monotonic()
        if now_mono < self._redis_dead_until:
            return self._mem.is_allowed(key)

        r = self._redis_getter()
        if r is None:
            return self._mem.is_allowed(key)

        try:
            res = await r.eval(
                _SLIDE_LUA,
                1,
                f"rate:{self.name}:{key}",
                str(time.time()),
                str(self.seconds),
                str(self.times),
            )
            # reset dead state on success
            self._redis_dead_until = 0.0
            return bool(int(res))
        except (RedisError, OSError, RuntimeError, Exception) as exc:  # noqa: BLE001
            # Mark Redis dead for a cooldown window, then fall back.
            self._redis_dead_until = now_mono + _REDIS_DEAD_COOLDOWN_S
            logger.warning(
                "Redis rate-limiter unavailable for '%s', using in-memory "
                "fallback: %s", self.name, exc
            )
            return self._mem.is_allowed(key)


def _default_redis_getter():
    """Lazy import avoids a hard dependency at module import time."""
    try:
        from app.core.database import get_redis
        return get_redis()
    except Exception:  # pragma: no cover
        return None


# --------------------------------------------------------------------------- #
# Client identification (honors X-Forwarded-For behind a trusted proxy)
# --------------------------------------------------------------------------- #
def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        # The leftmost entry is the original client when behind a proxy chain.
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# --------------------------------------------------------------------------- #
# Limiter instances (shared)
# --------------------------------------------------------------------------- #
from app.core.config import settings  # noqa: E402  (avoid circular import at top)

_predict_limiter = RateLimiter("predict", times=10, seconds=60,
                               enabled=settings.RATE_LIMIT_REDIS_ENABLED)
_analyze_limiter = RateLimiter("analyze", times=5, seconds=60,
                               enabled=settings.RATE_LIMIT_REDIS_ENABLED)
_chat_limiter = RateLimiter("chat", times=20, seconds=60,
                            enabled=settings.RATE_LIMIT_REDIS_ENABLED)
_news_limiter = RateLimiter("news", times=30, seconds=60,
                            enabled=settings.RATE_LIMIT_REDIS_ENABLED)


# --------------------------------------------------------------------------- #
# FastAPI dependencies
# --------------------------------------------------------------------------- #
async def limit_predict(request: Request):
    if not await _predict_limiter.is_allowed(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for predictions")


async def limit_analyze(request: Request):
    if not await _analyze_limiter.is_allowed(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for analysis")


async def limit_chat(request: Request):
    if not await _chat_limiter.is_allowed(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for chat")


async def limit_news(request: Request):
    if not await _news_limiter.is_allowed(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Rate limit exceeded for news")
