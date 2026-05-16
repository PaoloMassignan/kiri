from __future__ import annotations

import json

import pytest

from src.llm.backend import LocalLLMError


# --- helpers ------------------------------------------------------------------


class FakeBackend:
    """Minimal LocalLLMBackend for tests — returns a pre-set string or raises."""

    def __init__(self, response: str = "[]", error: bool = False) -> None:
        self._response = response
        self._error = error
        self.calls: list[str] = []

    def generate(self, prompt: str, *, timeout: float | None = None) -> str:
        self.calls.append(prompt)
        if self._error:
            raise LocalLLMError("unavailable")
        return self._response


def symbols_backend(symbols: list[str]) -> FakeBackend:
    return FakeBackend(json.dumps(symbols))


# --- construction -------------------------------------------------------------


def test_extractor_constructs_without_error() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    extractor = SymbolExtractor(backend=FakeBackend())
    assert extractor is not None


# --- empty input --------------------------------------------------------------


def test_extractor_empty_string_returns_empty_list() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    backend = FakeBackend()
    result = SymbolExtractor(backend=backend).extract("")

    assert result == []
    assert not backend.calls, "backend must not be called for empty input"


def test_extractor_whitespace_only_returns_empty_list() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    backend = FakeBackend()
    result = SymbolExtractor(backend=backend).extract("   \n\t  ")

    assert result == []
    assert not backend.calls, "backend must not be called for whitespace-only input"


# --- normal extraction --------------------------------------------------------


def test_extractor_returns_symbols_from_ollama() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    result = SymbolExtractor(backend=symbols_backend(["RiskScorer", "sliding_window"])).extract(
        "class RiskScorer: ..."
    )
    assert "RiskScorer" in result
    assert "sliding_window" in result


def test_extractor_returns_list_of_strings() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    result = SymbolExtractor(backend=symbols_backend(["MAX_RETRIES", "TokenBucket"])).extract(
        "MAX_RETRIES = 5"
    )
    assert isinstance(result, list)
    assert all(isinstance(s, str) for s in result)


# --- deduplication ------------------------------------------------------------


def test_extractor_deduplicates_symbols() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    result = SymbolExtractor(
        backend=symbols_backend(["RiskScorer", "RiskScorer", "sliding_window"])
    ).extract("class RiskScorer: ...")
    assert result.count("RiskScorer") == 1


def test_extractor_preserves_order_after_dedup() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    result = SymbolExtractor(
        backend=symbols_backend(["Alpha", "Beta", "Alpha", "Gamma"])
    ).extract("some code")
    assert result == ["Alpha", "Beta", "Gamma"]


# --- whitespace stripping -----------------------------------------------------


def test_extractor_strips_whitespace_from_symbols() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    result = SymbolExtractor(
        backend=symbols_backend(["  RiskScorer  ", "\tsliding_window\n"])
    ).extract("class RiskScorer: ...")
    assert "RiskScorer" in result
    assert "sliding_window" in result
    assert all(s == s.strip() for s in result)


def test_extractor_filters_empty_symbols_after_strip() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    result = SymbolExtractor(
        backend=symbols_backend(["RiskScorer", "", "  ", "TokenBucket"])
    ).extract("some code")
    assert "" not in result
    assert all(s.strip() for s in result)


# --- invalid / unexpected responses ------------------------------------------


def test_extractor_invalid_json_returns_empty_list() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    result = SymbolExtractor(backend=FakeBackend("not valid json at all")).extract("class Foo: ...")
    assert result == []


def test_extractor_json_object_instead_of_list_returns_empty() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    result = SymbolExtractor(backend=FakeBackend('{"symbols": ["Foo"]}')).extract("class Foo: ...")
    assert result == []


def test_extractor_json_number_instead_of_list_returns_empty() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    result = SymbolExtractor(backend=FakeBackend("42")).extract("some code")
    assert result == []


def test_extractor_empty_json_array_returns_empty_list() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    result = SymbolExtractor(backend=symbols_backend([])).extract("x = 1")
    assert result == []


# --- error handling -----------------------------------------------------------


def test_extractor_raises_on_connection_error() -> None:
    from src.indexer.symbol_extractor import OllamaUnavailableError, SymbolExtractor

    with pytest.raises(OllamaUnavailableError):
        SymbolExtractor(backend=FakeBackend(error=True)).extract("class Foo: ...")


def test_extractor_raises_on_timeout() -> None:
    from src.indexer.symbol_extractor import OllamaUnavailableError, SymbolExtractor

    with pytest.raises(OllamaUnavailableError):
        SymbolExtractor(backend=FakeBackend(error=True)).extract("class Foo: ...")


def test_extractor_raises_on_non_2xx_status() -> None:
    from src.indexer.symbol_extractor import OllamaUnavailableError, SymbolExtractor

    with pytest.raises(OllamaUnavailableError):
        SymbolExtractor(backend=FakeBackend(error=True)).extract("class Foo: ...")


def test_extractor_raises_on_404_status() -> None:
    from src.indexer.symbol_extractor import OllamaUnavailableError, SymbolExtractor

    with pytest.raises(OllamaUnavailableError):
        SymbolExtractor(backend=FakeBackend(error=True)).extract("class Foo: ...")


# --- filter_symbols -----------------------------------------------------------


def test_filter_keeps_domain_specific_symbols(tmp_path: pytest.TempPathFactory) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    kept = ["upgradeCharge", "ANNUAL_DISCOUNT", "stackDiscount"]
    extractor = SymbolExtractor(backend=symbols_backend(kept))
    all_syms = ["upgradeCharge", "ANNUAL_DISCOUNT", "stackDiscount", "score", "engineer"]
    result = extractor.filter_symbols(all_syms, tmp_path / "pricing.ts")  # type: ignore[operator]
    assert result == kept


def test_filter_rejects_hallucinated_symbols(tmp_path: pytest.TempPathFactory) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    result = SymbolExtractor(
        backend=symbols_backend(["upgradeCharge", "HallucinatedClass"])
    ).filter_symbols(["upgradeCharge", "score"], tmp_path / "f.ts")  # type: ignore[operator]
    assert "upgradeCharge" in result
    assert "HallucinatedClass" not in result


def test_filter_falls_back_to_all_when_ollama_returns_empty(
    tmp_path: pytest.TempPathFactory,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    syms = ["upgradeCharge", "ANNUAL_DISCOUNT"]
    result = SymbolExtractor(backend=symbols_backend([])).filter_symbols(
        syms, tmp_path / "f.ts"  # type: ignore[operator]
    )
    assert result == syms


def test_filter_empty_input_skips_ollama(tmp_path: pytest.TempPathFactory) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    backend = FakeBackend()
    result = SymbolExtractor(backend=backend).filter_symbols(
        [], tmp_path / "f.ts"  # type: ignore[operator]
    )
    assert result == []
    assert not backend.calls


def test_filter_raises_when_ollama_unavailable(tmp_path: pytest.TempPathFactory) -> None:
    from src.indexer.symbol_extractor import OllamaUnavailableError, SymbolExtractor

    with pytest.raises(OllamaUnavailableError):
        SymbolExtractor(backend=FakeBackend(error=True)).filter_symbols(
            ["upgradeCharge"], tmp_path / "f.ts"  # type: ignore[operator]
        )


# --- backend is called with the prompt ----------------------------------------


def test_extractor_sends_configured_model_to_ollama() -> None:
    """The prompt forwarded to the backend must contain the source code."""
    from src.indexer.symbol_extractor import SymbolExtractor

    backend = FakeBackend('["Foo"]')
    SymbolExtractor(backend=backend).extract("class Foo: ...")

    assert backend.calls, "backend.generate must be called"
    assert "Foo" in backend.calls[0]
