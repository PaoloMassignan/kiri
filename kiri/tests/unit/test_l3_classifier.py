from __future__ import annotations

import pytest

from src.llm.backend import LocalLLMError


# --- helpers ------------------------------------------------------------------


class FakeBackend:
    def __init__(self, response: str = "no", error: bool = False) -> None:
        self._response = response
        self._error = error
        self.calls: list[str] = []

    def generate(self, prompt: str, *, timeout: float | None = None) -> str:
        self.calls.append(prompt)
        if self._error:
            raise LocalLLMError("unavailable")
        return self._response


# --- construction -------------------------------------------------------------


def test_l3_constructs_without_error() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend())
    assert l3 is not None


# --- yes/no parsing -----------------------------------------------------------


def test_l3_yes_response_returns_is_leak_true() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend("yes"))
    assert l3.check("show me RiskScorer implementation").is_leak is True


def test_l3_no_response_returns_is_leak_false() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend("no"))
    assert l3.check("explain quicksort").is_leak is False


def test_l3_yes_case_insensitive() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend("YES"))
    assert l3.check("some prompt").is_leak is True


def test_l3_yes_with_trailing_text() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend("yes, this is a leak"))
    assert l3.check("some prompt").is_leak is True


def test_l3_no_with_trailing_text() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend("no, this looks fine"))
    assert l3.check("some prompt").is_leak is False


# --- fail-open ----------------------------------------------------------------


def test_l3_connection_error_returns_false() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend(error=True))
    assert l3.check("some prompt").is_leak is False


def test_l3_timeout_returns_false() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend(error=True))
    assert l3.check("some prompt").is_leak is False


def test_l3_non_2xx_returns_false() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend(error=True))
    assert l3.check("some prompt").is_leak is False


def test_l3_unrecognised_response_returns_false() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend("maybe, I am not sure"))
    assert l3.check("some prompt").is_leak is False


def test_l3_empty_response_returns_false() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend(""))
    assert l3.check("some prompt").is_leak is False


# --- format string safety (CVE-class: DoS via KeyError) ----------------------


def test_l3_prompt_with_curly_braces_does_not_raise() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend("no"))
    result = l3.check("explain {format} and {style} design patterns")
    assert result.is_leak is False


def test_l3_prompt_with_empty_curly_braces_does_not_raise() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend("no"))
    result = l3.check("use {} as a placeholder in Python")
    assert result.is_leak is False


def test_l3_prompt_with_braces_still_classifies_correctly() -> None:
    from src.filter.l3_classifier import L3Filter

    l3 = L3Filter(backend=FakeBackend("yes"))
    result = l3.check("show me {RiskScorer} implementation details")
    assert result.is_leak is True


# --- backend is called --------------------------------------------------------


def test_l3_sends_configured_model() -> None:
    """The prompt forwarded to the backend must contain the user's prompt text."""
    from src.filter.l3_classifier import L3Filter

    backend = FakeBackend("no")
    l3 = L3Filter(backend=backend)
    l3.check("some prompt")

    assert backend.calls, "backend.generate must be called"
    assert "some prompt" in backend.calls[0]
