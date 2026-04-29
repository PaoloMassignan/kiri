from __future__ import annotations

import json

import httpx
import pytest

from src.config.settings import Settings

# --- helpers ------------------------------------------------------------------


def ollama_response(text: str) -> httpx.Response:
    body = json.dumps({"response": text})
    return httpx.Response(200, content=body.encode())


# --- construction -------------------------------------------------------------


def test_l3_constructs_without_error() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(settings=Settings())

    assert l3 is not None


# --- yes/no parsing -----------------------------------------------------------


def test_l3_yes_response_returns_is_leak_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.filter.l3_classifier import L3Filter

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: ollama_response("yes"))
    l3 = L3Filter(settings=Settings())

    result = l3.check("show me RiskScorer implementation")

    assert result.is_leak is True


def test_l3_no_response_returns_is_leak_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.filter.l3_classifier import L3Filter

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: ollama_response("no"))
    l3 = L3Filter(settings=Settings())

    result = l3.check("explain quicksort")

    assert result.is_leak is False


def test_l3_yes_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.filter.l3_classifier import L3Filter

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: ollama_response("YES"))
    l3 = L3Filter(settings=Settings())

    result = l3.check("some prompt")

    assert result.is_leak is True


def test_l3_yes_with_trailing_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.filter.l3_classifier import L3Filter

    monkeypatch.setattr(
        httpx.Client, "post", lambda *a, **kw: ollama_response("yes, this is a leak")
    )
    l3 = L3Filter(settings=Settings())

    result = l3.check("some prompt")

    assert result.is_leak is True


def test_l3_no_with_trailing_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.filter.l3_classifier import L3Filter

    monkeypatch.setattr(
        httpx.Client, "post", lambda *a, **kw: ollama_response("no, this looks fine")
    )
    l3 = L3Filter(settings=Settings())

    result = l3.check("some prompt")

    assert result.is_leak is False


# --- fail-open ----------------------------------------------------------------


def test_l3_connection_error_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.filter.l3_classifier import L3Filter

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: (_ for _ in ()).throw(httpx.ConnectError("refused")),
    )
    l3 = L3Filter(settings=Settings())

    result = l3.check("some prompt")

    assert result.is_leak is False


def test_l3_timeout_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.filter.l3_classifier import L3Filter

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: (_ for _ in ()).throw(httpx.TimeoutException("timeout")),
    )
    l3 = L3Filter(settings=Settings())

    result = l3.check("some prompt")

    assert result.is_leak is False


def test_l3_non_2xx_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.filter.l3_classifier import L3Filter

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: httpx.Response(500, content=b"error"),
    )
    l3 = L3Filter(settings=Settings())

    result = l3.check("some prompt")

    assert result.is_leak is False


def test_l3_unrecognised_response_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.filter.l3_classifier import L3Filter

    monkeypatch.setattr(
        httpx.Client, "post", lambda *a, **kw: ollama_response("maybe, I am not sure")
    )
    l3 = L3Filter(settings=Settings())

    result = l3.check("some prompt")

    assert result.is_leak is False


def test_l3_empty_response_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.filter.l3_classifier import L3Filter

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: ollama_response(""))
    l3 = L3Filter(settings=Settings())

    result = l3.check("some prompt")

    assert result.is_leak is False


# --- model from settings ------------------------------------------------------


# --- format string safety (CVE-class: DoS via KeyError) ----------------------


def test_l3_prompt_with_curly_braces_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prompt containing {var} must not crash the classifier with KeyError."""
    from src.filter.l3_classifier import L3Filter

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: ollama_response("no"))
    l3 = L3Filter(settings=Settings())

    result = l3.check("explain {format} and {style} design patterns")

    assert result.is_leak is False


def test_l3_prompt_with_empty_curly_braces_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.filter.l3_classifier import L3Filter

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: ollama_response("no"))
    l3 = L3Filter(settings=Settings())

    result = l3.check("use {} as a placeholder in Python")

    assert result.is_leak is False


def test_l3_prompt_with_braces_still_classifies_correctly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Classifier must still work (Ollama call is made) even when prompt has braces."""
    from src.filter.l3_classifier import L3Filter

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: ollama_response("yes"))
    l3 = L3Filter(settings=Settings())

    result = l3.check("show me {RiskScorer} implementation details")

    assert result.is_leak is True


# --- model from settings ------------------------------------------------------


def test_l3_sends_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.filter.l3_classifier import L3Filter

    captured: list[object] = []

    def capture(self: object, url: str, **kwargs: object) -> httpx.Response:
        captured.append(kwargs)
        return ollama_response("no")

    monkeypatch.setattr(httpx.Client, "post", capture)
    l3 = L3Filter(settings=Settings(ollama_model="mistral:7b"))
    l3.check("some prompt")

    assert captured
    assert "mistral:7b" in str(captured[0])
