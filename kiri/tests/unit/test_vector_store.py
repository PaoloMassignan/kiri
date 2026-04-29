from __future__ import annotations

from pathlib import Path

# --- helpers ------------------------------------------------------------------


def make_store(tmp_path: Path):
    from src.store.vector_store import VectorStore

    return VectorStore(index_dir=tmp_path / "index")


def dummy_vector(seed: float, size: int = 8) -> list[float]:
    # deterministic unit vector for testing
    v = [seed * (i + 1) for i in range(size)]
    norm = sum(x**2 for x in v) ** 0.5
    return [x / norm for x in v]


def orthogonal_vector(size: int = 8) -> list[float]:
    # unit vector orthogonal to dummy_vector(1.0): only last component is non-zero
    v = [0.0] * size
    v[-1] = 1.0
    return v


# --- count / reset ------------------------------------------------------------


def test_vector_store_empty_on_creation(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    assert store.count() == 0


def test_vector_store_reset_clears_all_vectors(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("file1__0", dummy_vector(1.0), {"source_file": "file1.py", "chunk_index": "0"})

    store.reset()

    assert store.count() == 0


# --- add ----------------------------------------------------------------------


def test_vector_store_add_increases_count(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.add("file1__0", dummy_vector(1.0), {"source_file": "file1.py", "chunk_index": "0"})

    assert store.count() == 1


def test_vector_store_add_multiple_chunks(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.add("file1__0", dummy_vector(1.0), {"source_file": "file1.py", "chunk_index": "0"})
    store.add("file1__1", dummy_vector(2.0), {"source_file": "file1.py", "chunk_index": "1"})
    store.add("file2__0", dummy_vector(3.0), {"source_file": "file2.py", "chunk_index": "0"})

    assert store.count() == 3


# --- query --------------------------------------------------------------------


def test_vector_store_query_returns_top_k_results(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("file1__0", dummy_vector(1.0), {"source_file": "file1.py", "chunk_index": "0"})
    store.add("file2__0", dummy_vector(2.0), {"source_file": "file2.py", "chunk_index": "0"})
    store.add("file3__0", dummy_vector(3.0), {"source_file": "file3.py", "chunk_index": "0"})

    results = store.query(dummy_vector(1.0), top_k=2)

    assert len(results) == 2


def test_vector_store_query_similarity_in_range(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("file1__0", dummy_vector(1.0), {"source_file": "file1.py", "chunk_index": "0"})

    results = store.query(dummy_vector(1.0), top_k=1)

    assert len(results) == 1
    assert 0.0 <= results[0].similarity <= 1.0


def test_vector_store_query_identical_vector_has_high_similarity(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    v = dummy_vector(1.0)
    store.add("file1__0", v, {"source_file": "file1.py", "chunk_index": "0"})

    results = store.query(v, top_k=1)

    assert results[0].similarity > 0.99


def test_vector_store_query_best_match_first(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    # file1 is identical to query, file2 is orthogonal — guarantees distinct similarities
    store.add("file1__0", dummy_vector(1.0), {"source_file": "file1.py", "chunk_index": "0"})
    store.add("file2__0", orthogonal_vector(), {"source_file": "file2.py", "chunk_index": "0"})

    results = store.query(dummy_vector(1.0), top_k=2)

    assert results[0].source_file == "file1.py"
    assert results[0].similarity > results[1].similarity


def test_vector_store_query_returns_correct_metadata(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("file1__0", dummy_vector(1.0), {"source_file": "file1.py", "chunk_index": "0"})

    results = store.query(dummy_vector(1.0), top_k=1)

    assert results[0].doc_id == "file1__0"
    assert results[0].source_file == "file1.py"
    assert results[0].chunk_index == 0


def test_vector_store_query_empty_store_returns_empty(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    results = store.query(dummy_vector(1.0), top_k=3)

    assert results == []


def test_vector_store_query_top_k_capped_by_count(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("file1__0", dummy_vector(1.0), {"source_file": "file1.py", "chunk_index": "0"})

    # requesting top_k=5 but only 1 vector in store
    results = store.query(dummy_vector(1.0), top_k=5)

    assert len(results) == 1


# --- delete -------------------------------------------------------------------


def test_vector_store_delete_removes_all_chunks_for_file(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("file1__0", dummy_vector(1.0), {"source_file": "file1.py", "chunk_index": "0"})
    store.add("file1__1", dummy_vector(2.0), {"source_file": "file1.py", "chunk_index": "1"})
    store.add("file2__0", dummy_vector(3.0), {"source_file": "file2.py", "chunk_index": "0"})

    store.delete("file1")

    assert store.count() == 1
    results = store.query(dummy_vector(1.0), top_k=5)
    assert all(r.source_file == "file2.py" for r in results)


def test_vector_store_delete_nonexistent_prefix_does_not_raise(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.delete("ghost_file")  # must not raise


# --- persistence --------------------------------------------------------------


def test_vector_store_persists_across_instances(tmp_path: Path) -> None:
    from src.store.vector_store import VectorStore

    index_dir = tmp_path / "index"
    store1 = VectorStore(index_dir=index_dir)
    store1.add("file1__0", dummy_vector(1.0), {"source_file": "file1.py", "chunk_index": "0"})

    # create a new instance pointing to the same directory
    store2 = VectorStore(index_dir=index_dir)

    assert store2.count() == 1
