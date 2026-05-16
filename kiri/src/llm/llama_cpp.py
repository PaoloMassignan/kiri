from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from src.llm.backend import LocalLLMError

logger = logging.getLogger(__name__)

# llama-cpp-python is an optional dependency — only required for the native distribution.
# Install via: pip install -e ".[native]"
# For GPU acceleration:
#   CUDA:  CMAKE_ARGS="-DGGML_CUDA=on"  pip install llama-cpp-python
#   Metal: CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python
try:
    from llama_cpp import Llama  # type: ignore[import-untyped]
    _LLAMA_AVAILABLE = True
except ImportError:
    _LLAMA_AVAILABLE = False

_DEFAULT_MAX_TOKENS = 512
# Low temperature for deterministic classification and symbol extraction.
# SummaryGenerator benefits from slightly higher creativity, but 0.1 is
# safe across all three callers.
_DEFAULT_TEMPERATURE = 0.1


class LlamaCppBackend:
    """LocalLLMBackend that runs a GGUF model in-process via llama-cpp-python.

    Used by the native binary distribution (no Ollama sidecar required).
    The model file is stored at llm_model_path in config (default:
    /var/lib/kiri/models/qwen2.5-3b-q4.gguf, owned by the kiri service account).
    """

    def __init__(
        self,
        model_path: Path,
        n_ctx: int = 2048,
        n_threads: int = 0,
        n_gpu_layers: int = 0,
    ) -> None:
        """
        Args:
            model_path:    Path to the GGUF model file.
            n_ctx:         Context window in tokens.
            n_threads:     CPU threads to use; 0 = auto-detect (os.cpu_count()).
            n_gpu_layers:  Layers to offload to GPU; 0 = CPU-only, -1 = all layers.
        """
        if not _LLAMA_AVAILABLE:
            raise RuntimeError(
                "llama-cpp-python is not installed. "
                'Install the native extras: pip install -e ".[native]"'
            )
        if not model_path.exists():
            raise FileNotFoundError(
                f"GGUF model not found: {model_path}. "
                "Run `kiri install` to download the model, or set llm_model_path in config."
            )

        effective_threads = n_threads or (os.cpu_count() or 4)
        logger.info(
            "Loading GGUF model %s (n_ctx=%d, n_threads=%d, n_gpu_layers=%d)",
            model_path.name, n_ctx, effective_threads, n_gpu_layers,
        )
        self._llm: Any = Llama(
            model_path=str(model_path),
            n_ctx=n_ctx,
            n_threads=effective_threads,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
        )

    def generate(self, prompt: str, *, timeout: float | None = None) -> str:
        # llama-cpp-python is synchronous; timeout is not enforced by this backend.
        # Use create_chat_completion for instruct-tuned GGUF models (Qwen2.5-3B-Instruct,
        # Llama-3-8B-Instruct, etc.) — it applies the model's embedded chat template.
        try:
            output = self._llm.create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=_DEFAULT_MAX_TOKENS,
                temperature=_DEFAULT_TEMPERATURE,
            )
            text = str(output["choices"][0]["message"]["content"]).strip()
        except Exception as exc:
            raise LocalLLMError(f"llama-cpp inference failed: {exc}") from exc
        if not text:
            raise LocalLLMError("llama-cpp returned empty response")
        return text
