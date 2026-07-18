"""Pytest configuration + graceful dependency stubbing.

The project's heavy third-party dependencies (fastapi, pydantic[-settings],
httpx, redis, sqlalchemy, ...) are normally installed in the deployment / CI
environment. To keep the core behavioral tests runnable in a minimal sandbox
(and to keep CI honest about exercising the *real* code paths), we only inject
lightweight stubs when the real package is **not** importable.

  * In a sandbox with no deps installed -> stubs are injected, tests run.
  * In GitHub Actions (deps installed)   -> stubs are skipped, real code runs.

The stubbed boundaries are intentionally tiny: they only have to be real enough
for the modules under test (``ratelimit``, ``auth``, ``llm``, ``metrics``,
``config``) to import and behave correctly.
"""
from __future__ import annotations

import importlib
import os
import sys
import types

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _stub_fastapi() -> None:
    m = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code=400, detail=None, headers=None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
            self.headers = headers

    class Request:  # type hint only; not instantiated in tests
        pass

    class Depends:
        def __init__(self, dependency=None):
            self.dependency = dependency

    class FastAPI:
        pass

    class APIRouter:
        pass

    class Header:
        pass

    class Query:
        pass

    class Response:
        pass

    class JSONResponse:
        pass

    class WebSocket:
        pass

    class WebSocketDisconnect(Exception):
        pass

    class UploadFile:
        pass

    class File:
        pass

    class Body:
        pass

    class BackgroundTasks:
        pass

    class Form:
        pass

    class Cookie:
        pass

    class status:
        HTTP_200_OK = 200
        HTTP_201_CREATED = 201
        HTTP_400_BAD_REQUEST = 400
        HTTP_401_UNAUTHORIZED = 401
        HTTP_403_FORBIDDEN = 403
        HTTP_404_NOT_FOUND = 404
        HTTP_429_TOO_MANY_REQUESTS = 429
        HTTP_500_INTERNAL_SERVER_ERROR = 500
        HTTP_503_SERVICE_UNAVAILABLE = 503

    m.HTTPException = HTTPException
    m.Request = Request
    m.Depends = Depends
    m.FastAPI = FastAPI
    m.APIRouter = APIRouter
    m.Header = Header
    m.Query = Query
    m.Response = Response
    m.JSONResponse = JSONResponse
    m.WebSocket = WebSocket
    m.WebSocketDisconnect = WebSocketDisconnect
    m.UploadFile = UploadFile
    m.File = File
    m.Body = Body
    m.BackgroundTasks = BackgroundTasks
    m.Form = Form
    m.Cookie = Cookie
    m.status = status
    m.middleware = types.SimpleNamespace()
    sys.modules["fastapi"] = m

    cors = types.ModuleType("fastapi.middleware.cors")
    cors.CORSMiddleware = object
    sys.modules["fastapi.middleware.cors"] = cors


def _stub_pydantic_settings() -> None:
    m = types.ModuleType("pydantic_settings")

    class BaseSettings:
        """Minimal pydantic-settings stand-in.

        ``app/core/config.py`` reads almost all of its values via ``os.getenv``
        at class-attribute time, so a plain class carrying those defaults is
        sufficient for the modules under test.
        """

        def __init__(self, **kwargs):
            for name, val in list(vars(type(self)).items()):
                if not name.startswith("__"):
                    setattr(self, name, val)
            for name, val in kwargs.items():
                setattr(self, name, val)

        model_config: dict = {}
        Config = type("Config", (), {})

    m.BaseSettings = BaseSettings
    m.settings_customise_sources = None
    sys.modules["pydantic_settings"] = m


def _stub_pydantic() -> None:
    m = types.ModuleType("pydantic")

    def model_validator(*_a, **_k):
        def deco(func):
            return func

        return deco

    def field_validator(*_a, **_k):
        def deco(func):
            return func

        return deco

    class BaseModel:
        def model_dump(self, **_kw):
            return {k: v for k, v in vars(self).items() if not k.startswith("_")}

    def Field(*args, **_kw):
        return args[0] if args else None

    m.model_validator = model_validator
    m.field_validator = field_validator
    m.BaseModel = BaseModel
    m.Field = Field
    m.ConfigDict = lambda **k: k
    m.ValidationError = Exception
    m.TypeAdapter = object
    sys.modules["pydantic"] = m


def _stub_httpx() -> None:
    h = types.ModuleType("httpx")
    h.AsyncClient = object  # replaced by tests via monkeypatch when exercised
    h.HTTPError = Exception
    h.RequestError = Exception
    h.TimeoutException = Exception
    sys.modules["httpx"] = h


def _ensure_stubs() -> None:
    for mod, stubber in (
        ("fastapi", _stub_fastapi),
        ("pydantic_settings", _stub_pydantic_settings),
        ("pydantic", _stub_pydantic),
        ("httpx", _stub_httpx),
    ):
        try:
            importlib.import_module(mod)
        except Exception:
            stubber()


_ensure_stubs()
