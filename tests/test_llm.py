"""Behavioral tests for app.services.ai_engine.llm (Engineering Standard §6)."""
from __future__ import annotations

import asyncio

import app.services.ai_engine.llm as llm
from app.core import metrics
from app.services.ai_engine.llm import LLMUnavailable

from tests.helpers import make_httpx_fake, patch


def _reset_llm_cache():
    llm._llm_instance = None


def test_get_llm_off_returns_none():
    _reset_llm_cache()
    with patch(llm.settings, "LLM_PROVIDER", "off"):
        assert llm.get_llm() is None


def test_get_llm_cloud_configured():
    _reset_llm_cache()
    with patch(llm.settings, "LLM_PROVIDER", "cloud"), patch(
        llm.settings, "LLM_CLOUD_BASE_URL", "https://api.openai.com/v1"
    ), patch(llm.settings, "LLM_CLOUD_API_KEY", "sk-test"):
        inst = llm.get_llm()
        assert isinstance(inst, llm.OpenAICompatibleProvider)
        assert inst.is_configured() is True


def test_get_llm_hybrid_uses_ollama_when_cloud_absent():
    _reset_llm_cache()
    with patch(llm.settings, "LLM_PROVIDER", "hybrid"), patch(
        llm.settings, "LLM_CLOUD_API_KEY", ""
    ), patch(llm.settings, "LLM_OLLAMA_URL", "http://localhost:11434"), patch(
        llm.settings, "LLM_OLLAMA_MODEL", "llama3.1:8b"
    ):
        inst = llm.get_llm()
        assert isinstance(inst, llm.HybridLLM)
        # only ollama is configured -> it is the sole backend
        assert any(p.name == "ollama" for p in inst.providers)


def test_cloud_complete_success_increments_calls():
    metrics.reset()
    provider = llm.OpenAICompatibleProvider(
        "https://api.openai.com/v1", "sk-test", "gpt-4o-mini", 5
    )
    fake = make_httpx_fake(response={"choices": [{"message": {"content": " hello world "}}]})
    orig = llm.httpx
    llm.httpx = fake
    try:
        out = asyncio.run(provider.complete([{"role": "user", "content": "hi"}]))
    finally:
        llm.httpx = orig
    assert out == "hello world"  # output is stripped (treated as untrusted)
    assert metrics.snapshot()["counters"].get("llm_calls", 0) >= 1


def test_cloud_complete_failure_raises_llmunavailable():
    metrics.reset()
    provider = llm.OpenAICompatibleProvider(
        "https://api.openai.com/v1", "sk-test", "gpt-4o-mini", 5
    )

    class Boom(Exception):
        pass

    fake = make_httpx_fake(exception=Boom("network"))
    orig = llm.httpx
    llm.httpx = fake
    try:
        raised = False
        try:
            asyncio.run(provider.complete([{"role": "user", "content": "hi"}]))
        except LLMUnavailable:
            raised = True
    finally:
        llm.httpx = orig
    assert raised is True
    assert metrics.snapshot()["counters"].get("llm_failures", 0) >= 1
