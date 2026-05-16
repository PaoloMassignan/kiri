from __future__ import annotations

import logging
from pathlib import Path

from src.llm.backend import LocalLLMError

logger = logging.getLogger(__name__)

# llama-cpp-python is an optional dependency — only required for the native distribution.
# Install via: pip install -e ".[native]"
try:
    from llama_cpp import Llama  # type: ignore[import-untyped]
    _LLAMA_AVAILABLE = True
except ImportError:
    _LLAMA_AVAILABLE = False


class LlamaCppBackend:
    """LocalLLMBackend implementation that runs a GGUF model in-process via llama-cpp-python.

    Used by the native binary distribution (no Ollama sidecar required).
    The model file is downloaded once by `kiri install` and stored under the
    service account's data directory (/var/lib/kiri/models/).
    """

    def __init__(self, model_path: Path, n_ctx: int = 2048, n_threads: int = 4) -> None:
        if not _LLAMA_AVAILABLE:
            raise RuntimeError(
                "llama-cpp-python is not installed. "
                "Install the native distribution extras: pip install -e \".[native]\""
            )
        if not model_path.exists():
            raise FileNotFoundError(
                f"GGUF model not found: {model_path}. "
                "Run `kiri install` to download the model."
            )
        logger.info("Loading GGUF model from %s", model_path)
        self._llm = Llama(
            model_path=str(model_path),
            n_ctx=n_ctx,
            n_threads=n_threads,
            verbose=False,
        )

    def generate(self, prompt: str, *, timeout: float | None = None) -> str:
        # llama-cpp-python runs synchronously in-process; timeout is not enforced.
        try:
            output = self._llm(prompt, max_tokens=256, echo=False)
            text = output["choices"][0]["text"].strip()  # type: ignore[index]
        except Exception as exc:
            raise LocalLLMError(f"llama-cpp inference failed: {exc}") from exc
        if not text:
            raise LocalLLMError("llama-cpp returned empty response")
        return text
