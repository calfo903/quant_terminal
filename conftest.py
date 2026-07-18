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

    class _RouteCollector:
        """Minimal stand-in for a FastAPI/Starlette router.

        Router modules decorate endpoint functions at *import time*
        (``@router.get(...)``), so the stub must absorb those decorators and
        return the original function unchanged. We simply collect the
        endpoints so the module loads; we never exercise them in tests.
        """

        def __init__(self, *args, **kwargs):
            self.routes = []
            self.websocket_routes = []
            self.dependency_overrides = {}

        def _route(self, *args, **kwargs):
            def decorator(func):
                self.routes.append(func)
                return func

            return decorator

        get = _route
        post = _route
        put = _route
        delete = _route
        patch = _route
        options = _route
        head = _route
        trace = _route

        def websocket(self, *args, **kwargs):
            def decorator(func):
                self.websocket_routes.append(func)
                return func

            return decorator

        def include_router(self, *args, **kwargs):
            pass

        def add_api_route(self, *args, **kwargs):
            pass

        def add_api_websocket_route(self, *args, **kwargs):
            pass

    class FastAPI(_RouteCollector):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.middleware_stack = None
            self.exception_handlers = {}
            self.user_middleware = []

        def add_middleware(self, *args, **kwargs):
            pass

        def add_exception_handler(self, *args, **kwargs):
            pass

        def exception_handler(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def middleware(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

    class APIRouter(_RouteCollector):
        pass

    class _Param:
        """Stand-in for FastAPI dependency/parameter markers (Query, Header, ...).

        These are *called* at function-definition time
        (``def f(x: str = Query("1m", regex=...))``), so the stub must accept
        arbitrary positional/keyword arguments and store a reasonable default.
        """

        def __init__(self, *args, **kwargs):
            self.default = args[0] if args else None
            self.kwargs = kwargs

    class Header(_Param):
        pass

    class Query(_Param):
        pass

    class Path(_Param):
        pass

    class Body(_Param):
        pass

    class Form(_Param):
        pass

    class Cookie(_Param):
        pass

    class File(_Param):
        pass

    class UploadFile(_Param):
        pass

    class Response:
        def __init__(self, *args, **kwargs):
            self.body = args[0] if args else None

    class JSONResponse(Response):
        pass

    class WebSocket:
        pass

    class WebSocketDisconnect(Exception):
        pass

    class BackgroundTasks:
        def __init__(self, *args, **kwargs):
            pass

        def add_task(self, *args, **kwargs):
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
            # Copy only *setting* values (str/bool/int/dict/...) onto the
            # instance. Skip callables (methods) and nested classes (Config):
            # copying a method as an instance attribute would shadow the
            # descriptor and make `instance.some_method` return the raw (unbound)
            # function instead of a bound method, breaking `self`.
            for name, val in list(vars(type(self)).items()):
                if name.startswith("__"):
                    continue
                if callable(val) or isinstance(val, type):
                    continue
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


def _stub_heavy() -> None:
    """Stub the data-science / infra packages so modules that merely import
    them (charts, predictor, worker, ...) load in a dependency-free sandbox.

    Only invoked when the real packages are absent, so CI still runs real code.
    Each package is only stubbed if missing, so an environment that already has
    (say) numpy/pandas installed keeps the real implementations. The stubs are
    intentionally minimal: they only need to let ``import`` succeed; the
    modules under test never call into these libraries during the
    import-smoke / regression tests below.
    """
    if "numpy" not in sys.modules:
        np = types.ModuleType("numpy")
        np.ndarray = object
        np.array = lambda *a, **k: []
        np.float64 = float
        np.int64 = int
        np.nan = float("nan")
        sys.modules["numpy"] = np

    if "pandas" not in sys.modules:
        pd = types.ModuleType("pandas")
        pd.DataFrame = object
        pd.Series = object
        pd.to_numeric = lambda *a, **k: pd.Series
        pd.concat = lambda *a, **k: pd.Series
        pd.Timestamp = object
        pd.Timedelta = object
        pd.read_sql = lambda *a, **k: pd.DataFrame
        sys.modules["pandas"] = pd

    for name in ("torch", "joblib", "lightgbm", "cv2", "pytesseract", "transformers"):
        if name not in sys.modules:
            m = types.ModuleType(name)
            if name == "torch":
                # model_registry.py evaluates `torch.Tensor` in a method
                # annotation at import time, so the stub needs the attribute.
                m.Tensor = object
                m.device = lambda *a, **k: object()
                m.no_grad = object
                m.load = lambda *a, **k: None
                m.float32 = object
            sys.modules[name] = m

    ws = types.ModuleType("websockets")
    ws.connect = object
    sys.modules["websockets"] = ws

    sa = types.ModuleType("sqlalchemy")
    sa.text = lambda *a, **k: None
    sa.ext = types.ModuleType("sqlalchemy.ext")
    sa.ext.asyncio = types.ModuleType("sqlalchemy.ext.asyncio")
    sa.ext.asyncio.create_async_engine = lambda *a, **k: None
    sa.ext.asyncio.AsyncSession = object
    sa.ext.asyncio.async_sessionmaker = lambda *a, **k: object()
    sa.pool = types.ModuleType("sqlalchemy.pool")
    sa.pool.QueuePool = object
    sa.orm = types.ModuleType("sqlalchemy.orm")
    sa.orm.declarative_base = lambda *a, **k: object()
    sys.modules["sqlalchemy"] = sa
    sys.modules["sqlalchemy.ext"] = sa.ext
    sys.modules["sqlalchemy.ext.asyncio"] = sa.ext.asyncio
    sys.modules["sqlalchemy.pool"] = sa.pool
    sys.modules["sqlalchemy.orm"] = sa.orm

    rd = types.ModuleType("redis")
    rd.asyncio = types.ModuleType("redis.asyncio")
    rd.asyncio.Redis = object
    sys.modules["redis"] = rd
    sys.modules["redis.asyncio"] = rd.asyncio


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
    # Heavy data-science / infra packages: stub them all together iff absent.
    # Keyed on sqlalchemy because that (not numpy/pandas) is the package whose
    # absence means the full infra stack (DB, Redis, torch, ...) is missing.
    try:
        importlib.import_module("sqlalchemy")
    except Exception:
        _stub_heavy()


_ensure_stubs()
