"""Unit tests for LlamaCppBackend.

llama-cpp-python is an optional dependency and is NOT installed in the standard
test environment.  All tests mock the `llama_cpp` module so that the logic can
be exercised without a GPU or a GGUF model file.

Mocking strategy:
  - monkeypatch `src.llm.llama_cpp._LLAMA_AVAILABLE = True`
  - monkeypatch `src.llm.llama_cpp.Llama = FakeLlamaClass`
  The FakeLlamaClass is callable (acts as a constructor) and returns a
  FakeLlamaInstance whose `create_chat_completion` is configurable.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chat_response(text: str) -> dict:
    """Build a minimal create_chat_completion response dict."""
    return {"choices": [{"message": {"content": text}}]}


class FakeLlamaInstance:
    def __init__(self, response: str = "yes", error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    def create_chat_completion(self, messages, max_tokens=512, temperature=0.1, **kw):
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        if self._error:
            raise self._error
        return _chat_response(self._response)


def _patch_llama(monkeypatch, tmp_path: Path, response: str = "yes", error=None):
    """Patch the module so LlamaCppBackend can be constructed without the real library."""
    import src.llm.llama_cpp as mod

    instance = FakeLlamaInstance(response=response, error=error)

    def fake_constructor(**kwargs):
        return instance

    monkeypatch.setattr(mod, "_LLAMA_AVAILABLE", True, raising=False)
    monkeypatch.setattr(mod, "Llama", fake_constructor, raising=False)

    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake-gguf")
    return model_file, instance


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_raises_when_library_not_installed(tmp_path: Path, monkeypatch) -> None:
    import src.llm.llama_cpp as mod
    monkeypatch.setattr(mod, "_LLAMA_AVAILABLE", False, raising=False)

    with pytest.raises(RuntimeError, match="not installed"):
        mod.LlamaCppBackend(model_path=tmp_path / "model.gguf")


def test_raises_when_model_file_missing(tmp_path: Path, monkeypatch) -> None:
    import src.llm.llama_cpp as mod
    monkeypatch.setattr(mod, "_LLAMA_AVAILABLE", True, raising=False)
    monkeypatch.setattr(mod, "Llama", MagicMock(), raising=False)

    with pytest.raises(FileNotFoundError, match="GGUF model not found"):
        mod.LlamaCppBackend(model_path=tmp_path / "nonexistent.gguf")


def test_constructs_successfully(tmp_path: Path, monkeypatch) -> None:
    from src.llm.llama_cpp import LlamaCppBackend
    model_file, _ = _patch_llama(monkeypatch, tmp_path)

    backend = LlamaCppBackend(model_path=model_file)
    assert backend is not None


def test_n_threads_zero_uses_cpu_count(tmp_path: Path, monkeypatch) -> None:
    """n_threads=0 must not be passed to Llama as-is — auto-detect replaces it."""
    import src.llm.llama_cpp as mod
    captured: list[dict] = []

    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake")

    def fake_ctor(**kwargs):
        captured.append(kwargs)
        return FakeLlamaInstance()

    monkeypatch.setattr(mod, "_LLAMA_AVAILABLE", True, raising=False)
    monkeypatch.setattr(mod, "Llama", fake_ctor, raising=False)
    monkeypatch.setattr("os.cpu_count", lambda: 8)

    mod.LlamaCppBackend(model_path=model_file, n_threads=0)

    assert captured[0]["n_threads"] == 8


def test_explicit_n_threads_forwarded(tmp_path: Path, monkeypatch) -> None:
    import src.llm.llama_cpp as mod
    captured: list[dict] = []

    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake")

    def fake_ctor(**kwargs):
        captured.append(kwargs)
        return FakeLlamaInstance()

    monkeypatch.setattr(mod, "_LLAMA_AVAILABLE", True, raising=False)
    monkeypatch.setattr(mod, "Llama", fake_ctor, raising=False)

    mod.LlamaCppBackend(model_path=model_file, n_threads=2)

    assert captured[0]["n_threads"] == 2


def test_n_gpu_layers_forwarded(tmp_path: Path, monkeypatch) -> None:
    import src.llm.llama_cpp as mod
    captured: list[dict] = []

    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake")

    def fake_ctor(**kwargs):
        captured.append(kwargs)
        return FakeLlamaInstance()

    monkeypatch.setattr(mod, "_LLAMA_AVAILABLE", True, raising=False)
    monkeypatch.setattr(mod, "Llama", fake_ctor, raising=False)

    mod.LlamaCppBackend(model_path=model_file, n_gpu_layers=-1)

    assert captured[0]["n_gpu_layers"] == -1


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------


def test_generate_returns_model_response(tmp_path: Path, monkeypatch) -> None:
    from src.llm.llama_cpp import LlamaCppBackend
    model_file, _ = _patch_llama(monkeypatch, tmp_path, response="yes")

    backend = LlamaCppBackend(model_path=model_file)
    assert backend.generate("Is this a leak?") == "yes"


def test_generate_strips_whitespace(tmp_path: Path, monkeypatch) -> None:
    from src.llm.llama_cpp import LlamaCppBackend
    model_file, _ = _patch_llama(monkeypatch, tmp_path, response="  yes  \n")

    backend = LlamaCppBackend(model_path=model_file)
    assert backend.generate("prompt") == "yes"


def test_generate_sends_prompt_in_user_message(tmp_path: Path, monkeypatch) -> None:
    from src.llm.llama_cpp import LlamaCppBackend
    model_file, instance = _patch_llama(monkeypatch, tmp_path, response="no")

    backend = LlamaCppBackend(model_path=model_file)
    backend.generate("explain quicksort")

    assert instance.calls
    messages = instance.calls[0]["messages"]
    assert any(m["role"] == "user" and "explain quicksort" in m["content"] for m in messages)


def test_generate_raises_local_llm_error_on_inference_failure(
    tmp_path: Path, monkeypatch
) -> None:
    from src.llm.backend import LocalLLMError
    from src.llm.llama_cpp import LlamaCppBackend

    model_file, _ = _patch_llama(monkeypatch, tmp_path, error=RuntimeError("OOM"))

    backend = LlamaCppBackend(model_path=model_file)
    with pytest.raises(LocalLLMError, match="llama-cpp inference failed"):
        backend.generate("some prompt")


def test_generate_raises_on_empty_response(tmp_path: Path, monkeypatch) -> None:
    from src.llm.backend import LocalLLMError
    from src.llm.llama_cpp import LlamaCppBackend

    model_file, _ = _patch_llama(monkeypatch, tmp_path, response="")

    backend = LlamaCppBackend(model_path=model_file)
    with pytest.raises(LocalLLMError, match="empty response"):
        backend.generate("some prompt")


def test_generate_raises_on_whitespace_only_response(tmp_path: Path, monkeypatch) -> None:
    from src.llm.backend import LocalLLMError
    from src.llm.llama_cpp import LlamaCppBackend

    model_file, _ = _patch_llama(monkeypatch, tmp_path, response="   \n  ")

    backend = LlamaCppBackend(model_path=model_file)
    with pytest.raises(LocalLLMError, match="empty response"):
        backend.generate("some prompt")


def test_generate_timeout_accepted_but_not_enforced(tmp_path: Path, monkeypatch) -> None:
    """timeout= is accepted by the interface; llama-cpp-python is synchronous."""
    from src.llm.llama_cpp import LlamaCppBackend
    model_file, _ = _patch_llama(monkeypatch, tmp_path, response="ok")

    backend = LlamaCppBackend(model_path=model_file)
    result = backend.generate("prompt", timeout=5.0)
    assert result == "ok"


# ---------------------------------------------------------------------------
# Factory integration
# ---------------------------------------------------------------------------


def test_make_llm_backend_returns_llama_cpp_when_configured(
    tmp_path: Path, monkeypatch
) -> None:
    from src.config.settings import Settings
    from src.llm import make_llm_backend
    from src.llm.llama_cpp import LlamaCppBackend
    import src.llm.llama_cpp as mod

    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake")

    monkeypatch.setattr(mod, "_LLAMA_AVAILABLE", True, raising=False)
    monkeypatch.setattr(mod, "Llama", lambda **kw: FakeLlamaInstance(), raising=False)

    settings = Settings(
        llm_backend="llama_cpp",
        llm_model_path=str(model_file),
    )
    backend = make_llm_backend(settings)
    assert isinstance(backend, LlamaCppBackend)


def test_make_llm_backend_passes_n_ctx_from_settings(
    tmp_path: Path, monkeypatch
) -> None:
    from src.config.settings import Settings
    from src.llm import make_llm_backend
    import src.llm.llama_cpp as mod

    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake")
    captured: list[dict] = []

    def fake_ctor(**kwargs):
        captured.append(kwargs)
        return FakeLlamaInstance()

    monkeypatch.setattr(mod, "_LLAMA_AVAILABLE", True, raising=False)
    monkeypatch.setattr(mod, "Llama", fake_ctor, raising=False)

    settings = Settings(
        llm_backend="llama_cpp",
        llm_model_path=str(model_file),
        llm_n_ctx=4096,
        llm_n_gpu_layers=-1,
    )
    make_llm_backend(settings)

    assert captured[0]["n_ctx"] == 4096
    assert captured[0]["n_gpu_layers"] == -1
