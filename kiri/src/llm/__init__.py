from __future__ import annotations

import os
from pathlib import Path

from src.config.settings import Settings
from src.llm.backend import LocalLLMBackend, LocalLLMError
from src.llm.ollama import OllamaBackend


def make_llm_backend(settings: Settings) -> LocalLLMBackend:
    """Factory: returns the LocalLLMBackend configured in settings."""
    if settings.llm_backend == "llama_cpp":
        from src.llm.llama_cpp import LlamaCppBackend
        n_threads = settings.llm_n_threads or (os.cpu_count() or 4)
        return LlamaCppBackend(
            model_path=Path(settings.llm_model_path),
            n_ctx=settings.llm_n_ctx,
            n_threads=n_threads,
            n_gpu_layers=settings.llm_n_gpu_layers,
        )

    # Default: Ollama (Docker distribution)
    return OllamaBackend(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        default_timeout=settings.ollama_timeout_seconds,
    )


__all__ = ["LocalLLMBackend", "LocalLLMError", "make_llm_backend"]
