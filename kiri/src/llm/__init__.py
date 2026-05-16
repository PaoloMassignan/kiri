from __future__ import annotations

from src.config.settings import Settings
from src.llm.backend import LocalLLMBackend, LocalLLMError
from src.llm.ollama import OllamaBackend


def make_llm_backend(settings: Settings) -> LocalLLMBackend:
    """Factory: returns the configured LocalLLMBackend."""
    if settings.llm_backend == "llama_cpp":
        from pathlib import Path
        from src.llm.llama_cpp import LlamaCppBackend
        model_path = Path(settings.llm_model_path)
        return LlamaCppBackend(model_path=model_path)

    # Default: Ollama
    return OllamaBackend(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        default_timeout=settings.ollama_timeout_seconds,
    )


__all__ = ["LocalLLMBackend", "LocalLLMError", "make_llm_backend"]
