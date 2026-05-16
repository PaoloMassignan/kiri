from __future__ import annotations

import logging
from dataclasses import dataclass

from src.llm.backend import LocalLLMBackend, LocalLLMError

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
    def __init__(self, backend: LocalLLMBackend) -> None:
        self._backend = backend

    def check(self, prompt: str) -> L3Result:
        classification = _PROMPT_TEMPLATE.format(prompt=prompt)
        try:
            raw = self._backend.generate(classification).strip().lower()
        except LocalLLMError as exc:
            logger.warning("l3_classifier: backend unavailable: %s", exc)
            return L3Result(is_leak=False)
        return L3Result(is_leak=raw.startswith("yes"))
