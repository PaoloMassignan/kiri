from __future__ import annotations

import json

import httpx
import pytest

from src.config.settings import Settings

# --- helpers ------------------------------------------------------------------


def make_extractor() -> object:
    from src.indexer.symbol_extractor import SymbolExtractor

    return SymbolExtractor(settings=Settings())


def ollama_response(symbols: list[str]) -> httpx.Response:
    body = json.dumps({"response": json.dumps(symbols)})
    return httpx.Response(200, content=body.encode())


def ollama_response_raw(text: str) -> httpx.Response:
    body = json.dumps({"response": text})
    return httpx.Response(200, content=body.encode())


# --- construction -------------------------------------------------------------


def test_extractor_constructs_without_error() -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    extractor = SymbolExtractor(settings=Settings())

    assert extractor is not None


# --- empty input --------------------------------------------------------------


def test_extractor_empty_string_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    called = []

    def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        called.append(True)
        return ollama_response([])

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.extract("")

    assert result == []
    assert not called, "Ollama must not be called for empty input"


def test_extractor_whitespace_only_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    called = []

    def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        called.append(True)
        return ollama_response([])

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.extract("   \n\t  ")

    assert result == []
    assert not called, "Ollama must not be called for whitespace-only input"


# --- normal extraction --------------------------------------------------------


def test_extractor_returns_symbols_from_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: ollama_response(["RiskScorer", "sliding_window"]),
    )
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.extract("class RiskScorer: ...")

    assert "RiskScorer" in result
    assert "sliding_window" in result


def test_extractor_returns_list_of_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: ollama_response(["MAX_RETRIES", "TokenBucket"]),
    )
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.extract("MAX_RETRIES = 5")

    assert isinstance(result, list)
    assert all(isinstance(s, str) for s in result)


# --- deduplication ------------------------------------------------------------


def test_extractor_deduplicates_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: ollama_response(["RiskScorer", "RiskScorer", "sliding_window"]),
    )
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.extract("class RiskScorer: ...")

    assert result.count("RiskScorer") == 1


def test_extractor_preserves_order_after_dedup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: ollama_response(["Alpha", "Beta", "Alpha", "Gamma"]),
    )
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.extract("some code")

    assert result == ["Alpha", "Beta", "Gamma"]


# --- whitespace stripping -----------------------------------------------------


def test_extractor_strips_whitespace_from_symbols(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: ollama_response(["  RiskScorer  ", "\tsliding_window\n"]),
    )
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.extract("class RiskScorer: ...")

    assert "RiskScorer" in result
    assert "sliding_window" in result
    assert all(s == s.strip() for s in result)


def test_extractor_filters_empty_symbols_after_strip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: ollama_response(["RiskScorer", "", "  ", "TokenBucket"]),
    )
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.extract("some code")

    assert "" not in result
    assert all(s.strip() for s in result)


# --- invalid / unexpected responses ------------------------------------------


def test_extractor_invalid_json_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: ollama_response_raw("not valid json at all"),
    )
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.extract("class Foo: ...")

    assert result == []


def test_extractor_json_object_instead_of_list_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: ollama_response_raw('{"symbols": ["Foo"]}'),
    )
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.extract("class Foo: ...")

    assert result == []


def test_extractor_json_number_instead_of_list_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: ollama_response_raw("42"),
    )
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.extract("some code")

    assert result == []


def test_extractor_empty_json_array_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: ollama_response([]),
    )
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.extract("x = 1")

    assert result == []


# --- error handling -----------------------------------------------------------


def test_extractor_raises_on_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import OllamaUnavailableError, SymbolExtractor

    def raise_connect(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.Client, "post", raise_connect)
    extractor = SymbolExtractor(settings=Settings())

    with pytest.raises(OllamaUnavailableError):
        extractor.extract("class Foo: ...")


def test_extractor_raises_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import OllamaUnavailableError, SymbolExtractor

    def raise_timeout(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx.Client, "post", raise_timeout)
    extractor = SymbolExtractor(settings=Settings())

    with pytest.raises(OllamaUnavailableError):
        extractor.extract("class Foo: ...")


def test_extractor_raises_on_non_2xx_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import OllamaUnavailableError, SymbolExtractor

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: httpx.Response(500, content=b"internal server error"),
    )
    extractor = SymbolExtractor(settings=Settings())

    with pytest.raises(OllamaUnavailableError):
        extractor.extract("class Foo: ...")


def test_extractor_raises_on_404_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import OllamaUnavailableError, SymbolExtractor

    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: httpx.Response(404, content=b"not found"),
    )
    extractor = SymbolExtractor(settings=Settings())

    with pytest.raises(OllamaUnavailableError):
        extractor.extract("class Foo: ...")


# --- filter_symbols -----------------------------------------------------------


def test_filter_keeps_domain_specific_symbols(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    """Ollama returns a subset → only those are kept."""
    from src.indexer.symbol_extractor import SymbolExtractor

    kept = ["upgradeCharge", "ANNUAL_DISCOUNT", "stackDiscount"]
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: ollama_response(kept))
    extractor = SymbolExtractor(settings=Settings())

    all_syms = ["upgradeCharge", "ANNUAL_DISCOUNT", "stackDiscount", "score", "engineer"]
    result = extractor.filter_symbols(all_syms, tmp_path / "pricing.ts")

    assert result == kept


def test_filter_rejects_hallucinated_symbols(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    """Symbols Ollama invents that were not in the input are dropped."""
    from src.indexer.symbol_extractor import SymbolExtractor

    monkeypatch.setattr(
        httpx.Client, "post",
        lambda *a, **kw: ollama_response(["upgradeCharge", "HallucinatedClass"]),
    )
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.filter_symbols(["upgradeCharge", "score"], tmp_path / "f.ts")

    assert "upgradeCharge" in result
    assert "HallucinatedClass" not in result


def test_filter_falls_back_to_all_when_ollama_returns_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    """If Ollama returns [], keep all symbols (safe default — better over-protect)."""
    from src.indexer.symbol_extractor import SymbolExtractor

    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: ollama_response([]))
    extractor = SymbolExtractor(settings=Settings())

    syms = ["upgradeCharge", "ANNUAL_DISCOUNT"]
    result = extractor.filter_symbols(syms, tmp_path / "f.ts")

    assert result == syms


def test_filter_empty_input_skips_ollama(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    """Empty symbol list returns immediately without calling Ollama."""
    from src.indexer.symbol_extractor import SymbolExtractor

    called = []
    monkeypatch.setattr(
        httpx.Client, "post", lambda *a, **kw: called.append(True) or ollama_response([])
    )
    extractor = SymbolExtractor(settings=Settings())

    result = extractor.filter_symbols([], tmp_path / "f.ts")

    assert result == []
    assert not called


def test_filter_raises_when_ollama_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    """OllamaUnavailableError propagates so the caller can fall back."""
    from src.indexer.symbol_extractor import OllamaUnavailableError, SymbolExtractor

    monkeypatch.setattr(
        httpx.Client, "post",
        lambda *a, **kw: (_ for _ in ()).throw(httpx.ConnectError("refused")),
    )
    extractor = SymbolExtractor(settings=Settings())

    with pytest.raises(OllamaUnavailableError):
        extractor.filter_symbols(["upgradeCharge"], tmp_path / "f.ts")


# --- model used from settings -------------------------------------------------


def test_extractor_sends_configured_model_to_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.indexer.symbol_extractor import SymbolExtractor

    captured: list[object] = []

    def capture_post(self: object, url: str, **kwargs: object) -> httpx.Response:
        captured.append(kwargs)
        return ollama_response(["Foo"])

    monkeypatch.setattr(httpx.Client, "post", capture_post)

    settings = Settings(ollama_model="mistral:7b")
    extractor = SymbolExtractor(settings=settings)
    extractor.extract("class Foo: ...")

    assert captured
    payload = captured[0]
    assert isinstance(payload, dict)
    # model name must appear somewhere in what was sent
    assert "mistral:7b" in str(payload)
