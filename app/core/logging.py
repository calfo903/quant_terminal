"""Structured JSON logging (Engineering Standard §5.1).

Production logs are emitted as single-line JSON so they can be ingested by any
log aggregator (CloudWatch, Datadog, Loki, ELK, ...). Sensitive values are
redacted two ways:

  1. By *key*  — any extra/log field whose name matches a known secret key
     (``api_key``, ``token``, ``password``, ``authorization``, ...) has its
     value replaced with ``***REDACTED***``.
  2. By *value* — configured secret strings (API key, DB DSN, Redis URL, ...)
     are masked wherever they appear in the free-text message.

The module is dependency-light (stdlib only) and degrades gracefully: if the
config cannot be loaded it simply skips value-based redaction.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Iterable, List, Optional

# Field names whose *values* must be masked in structured logs.
_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "api-key",
        "password",
        "passwd",
        "pwd",
        "secret",
        "secrets",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "auth",
        "x_api_key",
        "bearer",
        "dsn",
        "connection",
        "connection_string",
    }
)
_MASK = "***REDACTED***"

# LogRecord attributes we never surface as structured "extra" fields.
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


def _secret_strings() -> List[str]:
    """Return configured secret values to mask anywhere in log text."""
    try:
        from app.core.config import settings
    except Exception:  # pragma: no cover - only if config is unavailable
        return []
    out: List[str] = []
    for raw in (
        getattr(settings, "API_KEY", ""),
        getattr(settings, "API_KEYS", ""),
        getattr(settings, "LLM_CLOUD_API_KEY", ""),
        getattr(settings, "LIVERATES_API_KEY", ""),
        getattr(settings, "META_API_TOKEN", ""),
        getattr(settings, "TIMESCALEDB_URL", ""),
        getattr(settings, "REDIS_URL", ""),
    ):
        if not raw:
            continue
        for piece in str(raw).split(","):
            piece = piece.strip()
            # only mask reasonably long, non-trivial substrings
            if piece and len(piece) >= 4:
                out.append(piece)
    return out


def _mask_text(text: str) -> str:
    for secret in _secret_strings():
        if secret and secret in text:
            text = text.replace(secret, _MASK)
    return text


def _redact_mapping(mapping: dict) -> dict:
    out: dict = {}
    for key, value in mapping.items():
        if str(key).lower() in _SENSITIVE_KEYS:
            out[key] = _MASK
        else:
            out[key] = value
    return out


class JsonFormatter(logging.Formatter):
    """Render a :class:`LogRecord` as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        msg = _mask_text(record.getMessage())
        log: dict = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": msg,
        }
        if record.filename and record.lineno:
            log["file"] = f"{record.filename}:{record.lineno}"

        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in _RESERVED and not k.startswith("_")
        }
        if extras:
            log["extra"] = _redact_mapping(extras)

        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        return json.dumps(log, default=str)


_CONFIGURED = False


def configure_logging(
    level: Optional[str] = None,
    use_json: bool = True,
    stream=None,
) -> None:
    """Install a root handler (JSON by default). Idempotent.

    Used in ``app/main.py`` at startup so the whole process emits structured
    logs. Calling it again simply replaces the root handler (no duplicates).
    """
    global _CONFIGURED
    try:
        from app.core.config import settings

        lvl = level or getattr(settings, "LOG_LEVEL", "INFO")
    except Exception:  # pragma: no cover
        lvl = level or "INFO"

    handler = logging.StreamHandler(stream or sys.stdout)
    if use_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
            )
        )

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(getattr(logging, str(lvl).upper(), logging.INFO))
    _CONFIGURED = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Return a named logger. Call after ``configure_logging`` for JSON output."""
    return logging.getLogger(name or __name__)
