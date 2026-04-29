from __future__ import annotations

from src.store.vector_store import QueryResult

# --- fakes --------------------------------------------------------------------


class FakeVectorStore:
    def __init__(self, results: list[QueryResult]) -> None:
        self._results = results

    def query(self, vector: list[float], top_k: int) -> list[QueryResult]:
        return self._results[:top_k]


class FakeEmbedder:
    def embed_one(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3, 0.4]


def make_result(doc_id: str, similarity: float, source: str = "engine.py") -> QueryResult:
    return QueryResult(
        doc_id=doc_id,
        similarity=similarity,
        source_file=source,
        chunk_index=0,
    )


# --- construction -------------------------------------------------------------


def test_l1_constructs_without_error() -> None:
    from src.filter.l1_similarity import L1Filter

    l1 = L1Filter(
        vector_store=FakeVectorStore([]),  # type: ignore[arg-type]
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
    )

    assert l1 is not None


# --- empty store --------------------------------------------------------------


def test_l1_empty_store_returns_zero_score() -> None:
    from src.filter.l1_similarity import L1Filter

    l1 = L1Filter(
        vector_store=FakeVectorStore([]),  # type: ignore[arg-type]
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
    )

    result = l1.check("how does RiskScorer work?")

    assert result.top_score == 0.0


def test_l1_empty_store_returns_empty_strings() -> None:
    from src.filter.l1_similarity import L1Filter

    l1 = L1Filter(
        vector_store=FakeVectorStore([]),  # type: ignore[arg-type]
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
    )

    result = l1.check("any prompt")

    assert result.top_doc_id == ""
    assert result.top_source_file == ""


# --- score extraction ---------------------------------------------------------


def test_l1_returns_highest_score_from_results() -> None:
    from src.filter.l1_similarity import L1Filter

    results = [
        make_result("engine__0", 0.95),
        make_result("engine__1", 0.80),
        make_result("engine__2", 0.60),
    ]
    l1 = L1Filter(
        vector_store=FakeVectorStore(results),  # type: ignore[arg-type]
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
    )

    result = l1.check("some prompt")

    assert result.top_score == 0.95


def test_l1_returns_doc_id_of_top_match() -> None:
    from src.filter.l1_similarity import L1Filter

    results = [
        make_result("engine__0", 0.95),
        make_result("scorer__1", 0.80),
    ]
    l1 = L1Filter(
        vector_store=FakeVectorStore(results),  # type: ignore[arg-type]
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
    )

    result = l1.check("some prompt")

    assert result.top_doc_id == "engine__0"


def test_l1_returns_source_file_of_top_match() -> None:
    from src.filter.l1_similarity import L1Filter

    results = [
        make_result("engine__0", 0.92, source="src/engine.py"),
        make_result("scorer__0", 0.75, source="src/scorer.py"),
    ]
    l1 = L1Filter(
        vector_store=FakeVectorStore(results),  # type: ignore[arg-type]
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
    )

    result = l1.check("some prompt")

    assert result.top_source_file == "src/engine.py"


def test_l1_single_result_is_used_as_top() -> None:
    from src.filter.l1_similarity import L1Filter

    results = [make_result("only__0", 0.55, source="only.py")]
    l1 = L1Filter(
        vector_store=FakeVectorStore(results),  # type: ignore[arg-type]
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
    )

    result = l1.check("prompt")

    assert result.top_score == 0.55
    assert result.top_doc_id == "only__0"
    assert result.top_source_file == "only.py"


# --- top_k --------------------------------------------------------------------


def test_l1_queries_with_top_k_5() -> None:
    from src.filter.l1_similarity import L1Filter

    captured: list[int] = []

    class CapturingStore:
        def query(self, vector: list[float], top_k: int) -> list[QueryResult]:
            captured.append(top_k)
            return []

    l1 = L1Filter(
        vector_store=CapturingStore(),  # type: ignore[arg-type]
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
    )
    l1.check("prompt")

    assert captured == [5]
