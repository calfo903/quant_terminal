"""Import-smoke + regression tests for module-level wiring.

These guard against the class of bug found during deep analysis: a module
that *uses* a name (``settings`` / ``asyncio``) without *importing* it, which
crashes at request/startup time with a ``NameError``. They also verify the
fixed behavior still works (e.g. ``/symbols`` returns the catalog).
"""
from __future__ import annotations

import asyncio as real_asyncio

import app.api.v1.charts as charts
import app.services.ai_engine.predictor as predictor
import app.worker as worker


async def test_charts_imports_settings_and_symbols_works():
    # Regression: charts.py called settings.symbol_catalog() without importing
    # settings -> NameError on GET /api/v1/charts/symbols.
    assert charts.settings is not None
    # `symbols` is an async endpoint, so it must be awaited in the test.
    catalog = await charts.symbols()
    assert isinstance(catalog, dict)
    assert "crypto" in catalog and "forex_majors" in catalog and "commodities" in catalog


def test_predictor_imports_asyncio():
    # Regression: predictor.py used asyncio.to_thread without importing asyncio
    # -> NameError on every prediction / plan / WS prediction.
    # Note: `predictor` here is the *module* (imported `as predictor`); the
    # class is `Predictor` and the singleton instance is `predictor.predictor`.
    assert predictor.asyncio is real_asyncio
    assert callable(predictor.Predictor.predict)
    assert callable(predictor.predictor.predict)


def test_worker_imports_settings():
    # Regression: worker.py used settings.* without importing settings ->
    # NameError on `python -m app.worker` startup.
    assert hasattr(worker, "settings")
    assert worker.settings is not None
