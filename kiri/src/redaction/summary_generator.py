from __future__ import annotations

import logging

from src.llm.backend import LocalLLMBackend, LocalLLMError

logger = logging.getLogger(__name__)

_TIMEOUT = 60.0

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
    def __init__(self, backend: LocalLLMBackend) -> None:
        self._backend = backend

    def generate(self, chunk_id: str, chunk_text: str, symbol_name: str) -> str:
        prompt = _PROMPT_TEMPLATE.format(
            symbol_name=symbol_name,
            chunk_text=chunk_text,
        )
        try:
            return self._backend.generate(prompt, timeout=_TIMEOUT)
        except LocalLLMError as exc:
            raise SummaryGenerationError(str(exc)) from exc
