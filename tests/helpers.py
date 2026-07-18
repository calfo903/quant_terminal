"""Shared helpers for the behavioral test-suite (no third-party deps)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Optional

from types import SimpleNamespace


class FakeRequest:
    """Minimal stand-in for a Starlette/FastAPI Request.

    Implements just the surface used by ``require_api_key`` and the ratelimit
    client-IP helpers: ``url.path``, ``headers.get``, ``query_params.get`` and
    ``client.host``.
    """

    def __init__(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        query: Optional[Dict[str, str]] = None,
        client_host: str = "127.0.0.1",
    ) -> None:
        self.url = SimpleNamespace(path=path)
        self.headers = headers or {}
        self.query_params = query or {}
        self.client = SimpleNamespace(host=client_host)


@contextmanager
def patch(obj: Any, attr: str, value: Any):
    """Set ``obj.attr = value`` for the duration of the block, then restore."""
    had = attr in vars(obj)
    original = getattr(obj, attr, None)
    setattr(obj, attr, value)
    try:
        yield
    finally:
        if had:
            setattr(obj, attr, original)
        else:
            try:
                delattr(obj, attr)
            except Exception:
                pass


def make_httpx_fake(
    response: Optional[Dict[str, Any]] = None,
    exception: Optional[BaseException] = None,
):
    """Build a drop-in ``httpx`` module whose AsyncClient returns ``response``.

    Inject it via ``monkeypatch.setattr(llm_module, "httpx", make_httpx_fake(...))``
    to exercise the LLM providers without any network call.
    """

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            if exception is not None:
                raise exception
            return FakeResponse(response)

    class Module:
        HTTPError = Exception
        RequestError = Exception
        TimeoutException = Exception

    # Class bodies can't see the enclosing function scope, so assign after.
    Module.AsyncClient = AsyncClient
    return Module()
