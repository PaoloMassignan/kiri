from __future__ import annotations

import json
import logging
from pathlib import Path

from src.llm.backend import LocalLLMBackend, LocalLLMError

_TIMEOUT = 30.0

_EXTRACT_TEMPLATE = (
    "You are a code analysis tool. "
    "List all proprietary symbol names (class names, function names, constants) "
    "found in the following code. "
    "Reply with a JSON array of strings only, no explanation.\n\n"
    "Code:\n{code}"
)

_FILTER_TEMPLATE = (
    "You are a code security tool.\n"
    "File: {filename}\n\n"
    "Preview:\n{preview}\n\n"
    "Symbol candidates: {symbols}\n\n"
    "Which of these are domain-specific business logic symbols (proprietary to this codebase)?\n"
    "Exclude generic programming terms such as: "
    "get, set, run, load, save, parse, fetch, validate, compute, process, convert, "
    "update, delete, create, handle, format, init, start, stop, reset, check, find, "
    "build, make, apply, use, add, remove, encode, decode, read, write, open, close.\n"
    "Reply with a JSON array of strings only. No explanation."
)

_PREVIEW_LINES = 20

logger = logging.getLogger(__name__)


class OllamaUnavailableError(Exception):
    pass


class SymbolExtractor:
    def __init__(self, backend: LocalLLMBackend) -> None:
        self._backend = backend

    def extract(self, text: str) -> list[str]:
        """Extract proprietary symbol names from raw code text."""
        if not text.strip():
            return []
        prompt = _EXTRACT_TEMPLATE.format(code=text)
        raw = self._call(prompt)
        return _parse_symbols(raw)

    def filter_symbols(self, symbols: list[str], file_path: Path) -> list[str]:
        """
        Filter AST-extracted symbols to domain-specific ones using the LLM backend.

        Only returns symbols that were in the original list (prevents hallucination).
        Falls back to the full list on parse error.
        """
        if not symbols:
            return symbols

        try:
            preview = _read_preview(file_path)
        except Exception:
            preview = ""

        prompt = _FILTER_TEMPLATE.format(
            filename=file_path.name,
            preview=preview,
            symbols=json.dumps(symbols),
        )
        raw = self._call(prompt)
        filtered = _parse_symbols(raw)

        original = set(symbols)
        result = [s for s in filtered if s in original]
        return result if result else symbols

    def _call(self, prompt: str) -> str:
        try:
            return self._backend.generate(prompt, timeout=_TIMEOUT)
        except LocalLLMError as exc:
            raise OllamaUnavailableError(str(exc)) from exc


def _read_preview(file_path: Path, lines: int = _PREVIEW_LINES) -> str:
    text = file_path.read_text(encoding="utf-8", errors="replace")
    return "\n".join(text.splitlines()[:lines])


def _parse_symbols(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.debug("symbol_extractor: invalid JSON from backend: %r", raw)
        return []

    if not isinstance(parsed, list):
        logger.debug("symbol_extractor: expected list, got %r", type(parsed))
        return []

    symbols = [s.strip() for s in parsed if isinstance(s, str)]
    symbols = [s for s in symbols if s]
    return list(dict.fromkeys(symbols))
