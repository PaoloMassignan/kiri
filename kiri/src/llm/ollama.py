from __future__ import annotations

import logging

import httpx

from src.llm.backend import LocalLLMError

_PATH = "/api/generate"
logger = logging.getLogger(__name__)


class OllamaBackend:
    """LocalLLMBackend implementation that calls a running Ollama service over HTTP."""

    def __init__(self, base_url: str, model: str, default_timeout: float = 30.0) -> None:
        self._url = base_url.rstrip("/") + _PATH
        self._model = model
        self._default_timeout = default_timeout

    def generate(self, prompt: str, *, timeout: float | None = None) -> str:
        t = timeout if timeout is not None else self._default_timeout
        client = httpx.Client(timeout=t)
        try:
            response = client.post(
                self._url,
                json={"model": self._model, "prompt": prompt, "stream": False},
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise LocalLLMError(f"Ollama unavailable: {exc}") from exc
        finally:
            client.close()

        if response.status_code < 200 or response.status_code >= 300:
            raise LocalLLMError(f"Ollama returned HTTP {response.status_code}")

        raw = str(response.json().get("response", "")).strip()
        if not raw:
            raise LocalLLMError("Ollama returned empty response")
        return raw
