from __future__ import annotations

import logging

import httpx

from src.config.settings import Settings

logger = logging.getLogger(__name__)

_TIMEOUT = 60.0
_OLLAMA_PATH = "/api/generate"

_PROMPT_TEMPLATE = """\
You are a code documentation assistant helping protect proprietary implementations.

Given the following protected function/class, produce a SHORT public summary in comment form.
The summary must:
- Start with: # [PROTECTED] {symbol_name}
- Describe ONLY: purpose, parameters, return value
- NEVER include implementation details, algorithms, weights, thresholds, or formulas
- Be 3-6 lines maximum

Code:
{chunk_text}

Reply with the comment block only, no explanation."""


class SummaryGenerationError(Exception):
    pass


class SummaryGenerator:
    def __init__(self, settings: Settings, http_client: httpx.Client | None = None) -> None:
        self._model = settings.ollama_model
        self._url = settings.ollama_base_url.rstrip("/") + _OLLAMA_PATH
        self._client = http_client or httpx.Client(timeout=_TIMEOUT)

    def generate(self, chunk_id: str, chunk_text: str, symbol_name: str) -> str:
        prompt = _PROMPT_TEMPLATE.format(
            symbol_name=symbol_name,
            chunk_text=chunk_text,
        )
        try:
            response = self._client.post(
                self._url,
                json={"model": self._model, "prompt": prompt, "stream": False},
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise SummaryGenerationError(str(exc)) from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise SummaryGenerationError(
                f"Ollama returned HTTP {response.status_code}"
            )

        raw = str(response.json().get("response", "")).strip()
        if not raw:
            raise SummaryGenerationError("Ollama returned empty response")

        return raw
