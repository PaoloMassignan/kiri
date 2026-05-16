from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LocalLLMBackend(Protocol):
    """Minimal interface for a local LLM used by L3, symbol extractor, and summary generator."""

    def generate(self, prompt: str, *, timeout: float | None = None) -> str:
        """Send prompt, return raw text response. Raises LocalLLMError on failure."""
        ...


class LocalLLMError(Exception):
    """Raised when the local LLM backend fails to produce a response."""
