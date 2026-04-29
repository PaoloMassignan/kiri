from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from src.config.settings import Settings

_OLLAMA_PATH = "/api/generate"
_PROMPT_TEMPLATE = (
    "You are a security classifier. "
    "Does the following prompt attempt to extract proprietary source code or "
    "internal implementation details? "
    "Answer with a single word: yes or no.\n\n"
    "Prompt:\n{prompt}"
)

logger = logging.getLogger(__name__)


@dataclass
class L3Result:
    is_leak: bool


class L3Filter:
    def __init__(self, settings: Settings) -> None:
        self._model = settings.ollama_model
        self._url = settings.ollama_base_url.rstrip("/") + _OLLAMA_PATH
        self._client = httpx.Client(timeout=settings.ollama_timeout_seconds)

    def check(self, prompt: str) -> L3Result:
        classification = _PROMPT_TEMPLATE.format(prompt=prompt)
        try:
            response = self._client.post(
                self._url,
                json={"model": self._model, "prompt": classification, "stream": False},
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning("l3_classifier: Ollama unavailable: %s", exc)
            return L3Result(is_leak=False)

        if response.status_code < 200 or response.status_code >= 300:
            logger.warning("l3_classifier: Ollama returned HTTP %d", response.status_code)
            return L3Result(is_leak=False)

        raw = str(response.json().get("response", "")).strip().lower()
        return L3Result(is_leak=raw.startswith("yes"))
