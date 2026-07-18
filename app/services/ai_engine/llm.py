from typing import Dict, List, Optional
from app.core.logging import get_logger

try:  # httpx is a required dependency (see requirements.txt)
    import httpx
except Exception:  # pragma: no cover - only if httpx is missing
    httpx = None  # type: ignore

from app.core.config import settings
from app.core import metrics

logger = get_logger(__name__)


class LLMUnavailable(Exception):
    """Raised when no configured LLM backend could produce a completion."""


class BaseLLMProvider:
    name = "base"

    def is_configured(self) -> bool:
        return False

    async def complete(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        raise NotImplementedError


class OpenAICompatibleProvider(BaseLLMProvider):
    """OpenAI Chat Completions API (also covers DeepSeek, Groq, Together, ...)."""

    name = "cloud"

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 30.0):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or "gpt-4o-mini"
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    async def complete(self, messages, max_tokens=None, temperature=None):
        if httpx is None:
            raise LLMUnavailable("httpx not installed")
        max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
        }
        metrics.inc("llm_calls")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:  # noqa: BLE001
            logger.debug("cloud LLM failed: %s", e)
            metrics.inc("llm_failures")
            raise LLMUnavailable(str(e))


class OllamaProvider(BaseLLMProvider):
    """Local Ollama server (https://ollama.com) - private, no token cost."""

    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 60.0):
        self.base_url = (base_url or "").rstrip("/")
        self.model = model or "llama3.1:8b"
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.base_url)

    async def complete(self, messages, max_tokens=None, temperature=None):
        if httpx is None:
            raise LLMUnavailable("httpx not installed")
        max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        temperature = temperature if temperature is not None else settings.LLM_TEMPERATURE
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": float(temperature), "num_predict": int(max_tokens)},
        }
        metrics.inc("llm_calls")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["message"]["content"].strip()
        except Exception as e:  # noqa: BLE001
            logger.debug("ollama LLM failed: %s", e)
            metrics.inc("llm_failures")
            raise LLMUnavailable(str(e))


class HybridLLM(BaseLLMProvider):
    """Tries each configured backend in order; all fail -> LLMUnavailable."""

    name = "hybrid"

    def __init__(self, providers: List[BaseLLMProvider]):
        self.providers = [p for p in providers if p.is_configured()]

    def is_configured(self) -> bool:
        return bool(self.providers)

    async def complete(self, messages, max_tokens=None, temperature=None):
        if not self.providers:
            raise LLMUnavailable("no LLM backend configured")
        last_err: Optional[Exception] = None
        for p in self.providers:
            try:
                return await p.complete(messages, max_tokens, temperature)
            except LLMUnavailable as e:
                last_err = e
                logger.debug("LLM backend '%s' unavailable: %s", p.name, e)
                continue
        raise LLMUnavailable(f"all LLM backends failed: {last_err}")


def _build_hybrid() -> Optional[BaseLLMProvider]:
    cloud = OpenAICompatibleProvider(
        settings.LLM_CLOUD_BASE_URL, settings.LLM_CLOUD_API_KEY,
        settings.LLM_CLOUD_MODEL, settings.LLM_TIMEOUT,
    )
    ollama = OllamaProvider(
        settings.LLM_OLLAMA_URL, settings.LLM_OLLAMA_MODEL, settings.LLM_TIMEOUT + 30,
    )
    hybrid = HybridLLM([cloud, ollama])
    return hybrid if hybrid.is_configured() else None


_llm_instance: Optional[BaseLLMProvider] = None


def get_llm() -> Optional[BaseLLMProvider]:
    """Return the configured LLM backend, or None to signal 'use heuristic'.

    Cached after first call. Provider is chosen by ``LLM_PROVIDER``:
      off     -> None (always heuristic/offline)
      cloud   -> OpenAI-compatible only
      ollama  -> local Ollama only
      hybrid  -> cloud then ollama; None if neither is configured
    """
    global _llm_instance
    if _llm_instance is not None:
        return _llm_instance
    provider = (getattr(settings, "LLM_PROVIDER", "off") or "off").lower()
    if provider == "off":
        _llm_instance = None
    elif provider == "cloud":
        inst = OpenAICompatibleProvider(
            settings.LLM_CLOUD_BASE_URL, settings.LLM_CLOUD_API_KEY,
            settings.LLM_CLOUD_MODEL, settings.LLM_TIMEOUT,
        )
        _llm_instance = inst if inst.is_configured() else None
    elif provider == "ollama":
        inst = OllamaProvider(
            settings.LLM_OLLAMA_URL, settings.LLM_OLLAMA_MODEL, settings.LLM_TIMEOUT + 30,
        )
        _llm_instance = inst if inst.is_configured() else None
    elif provider == "hybrid":
        _llm_instance = _build_hybrid()
    else:
        _llm_instance = None
    return _llm_instance
