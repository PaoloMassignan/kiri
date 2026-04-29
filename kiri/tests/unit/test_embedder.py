from __future__ import annotations

import pytest

from src.config.settings import Settings

# --- helpers ------------------------------------------------------------------


def make_embedder() -> object:
    from src.indexer.embedder import Embedder

    return Embedder(settings=Settings())


# --- basic output -------------------------------------------------------------


def test_embedder_returns_one_vector_per_text() -> None:
    from src.indexer.embedder import Embedder

    embedder = Embedder(settings=Settings())
    texts = ["hello world", "foo bar", "baz qux"]

    result = embedder.embed(texts)

    assert len(result) == 3


def test_embedder_vectors_have_consistent_dimension() -> None:
    from src.indexer.embedder import Embedder

    embedder = Embedder(settings=Settings())
    texts = ["first text", "second text", "third text"]

    result = embedder.embed(texts)
    dims = {len(v) for v in result}

    assert len(dims) == 1  # all same dimension


def test_embedder_vector_dimension_is_positive() -> None:
    from src.indexer.embedder import Embedder

    embedder = Embedder(settings=Settings())

    result = embedder.embed(["some text"])

    assert len(result[0]) > 0


def test_embedder_vectors_are_floats() -> None:
    from src.indexer.embedder import Embedder

    embedder = Embedder(settings=Settings())

    result = embedder.embed(["some text"])

    assert all(isinstance(v, float) for v in result[0])


# --- determinism --------------------------------------------------------------


def test_embedder_same_text_produces_same_vector() -> None:
    from src.indexer.embedder import Embedder

    embedder = Embedder(settings=Settings())
    text = "RiskScorer sliding window deduplication"

    v1 = embedder.embed([text])[0]
    v2 = embedder.embed([text])[0]

    assert v1 == v2


def test_embedder_different_texts_produce_different_vectors() -> None:
    from src.indexer.embedder import Embedder

    embedder = Embedder(settings=Settings())

    v1 = embedder.embed(["def risk_scorer(): pass"])[0]
    v2 = embedder.embed(["how to bake a cake"])[0]

    assert v1 != v2


# --- embed_one ----------------------------------------------------------------


def test_embedder_embed_one_matches_embed_batch() -> None:
    from src.indexer.embedder import Embedder

    embedder = Embedder(settings=Settings())
    text = "class RiskScorer:"

    single = embedder.embed_one(text)
    batch = embedder.embed([text])[0]

    assert single == batch


def test_embedder_embed_one_returns_list_of_float() -> None:
    from src.indexer.embedder import Embedder

    embedder = Embedder(settings=Settings())

    result = embedder.embed_one("some code")

    assert isinstance(result, list)
    assert all(isinstance(v, float) for v in result)


# --- model loaded once --------------------------------------------------------


def test_embedder_model_not_reloaded_on_repeated_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.indexer.embedder import Embedder

    load_count = 0
    original_init = Embedder.__init__

    def counting_init(self: Embedder, settings: Settings) -> None:
        nonlocal load_count
        load_count += 1
        original_init(self, settings)

    monkeypatch.setattr(Embedder, "__init__", counting_init)

    e = Embedder(settings=Settings())
    e.embed(["first call"])
    e.embed(["second call"])
    e.embed(["third call"])

    # model should be loaded once at construction, not on each embed call
    assert load_count == 1


# --- empty input --------------------------------------------------------------


def test_embedder_empty_list_returns_empty_list() -> None:
    from src.indexer.embedder import Embedder

    embedder = Embedder(settings=Settings())

    result = embedder.embed([])

    assert result == []
