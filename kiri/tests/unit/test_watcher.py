from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from src.indexer.chunker import Chunk
from src.indexer.symbol_extractor import OllamaUnavailableError

# --- fakes --------------------------------------------------------------------


class FakeVectorStore:
    def __init__(self) -> None:
        self.added: list[tuple[str, list[float], dict[str, str]]] = []
        self.deleted: list[str] = []

    def add(self, doc_id: str, vector: list[float], metadata: dict[str, str]) -> None:
        self.added.append((doc_id, vector, metadata))

    def delete(self, doc_id_prefix: str) -> None:
        self.deleted.append(doc_id_prefix)

    def query(self, vector: list[float], top_k: int) -> list[object]:
        return []

    def count(self) -> int:
        return len(self.added)

    def count_prefix(self, prefix: str) -> int:
        return sum(1 for doc_id, _, _ in self.added if doc_id.startswith(prefix + "__"))


class FakeSymbolStore:
    def __init__(self) -> None:
        self.added: list[tuple[str, list[str]]] = []
        self.removed: list[str] = []

    def add(self, source_file: str, symbols: list[str]) -> None:
        self.added.append((source_file, symbols))

    def remove(self, source_file: str) -> None:
        self.removed.append(source_file)


class FakeSecretsStore:
    def __init__(
        self,
        paths: list[Path],
        secrets_path: Path | None = None,
        glob_rules: list[str] | None = None,
        glob_expanded: dict[str, list[Path]] | None = None,
    ) -> None:
        self._paths = paths
        self._glob_rules = glob_rules or []
        self._glob_expanded = glob_expanded or {}
        self.secrets_path = secrets_path or Path("/fake/.kiri/secrets")

    def list_paths(self) -> list[Path]:
        return list(self._paths)

    def list_glob_rules(self) -> list[str]:
        return list(self._glob_rules)

    def expand_glob(self, pattern: str) -> list[Path]:
        return list(self._glob_expanded.get(pattern, []))


class FakeEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(i)] * 4 for i in range(len(texts))]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class FakeExtractor:
    def __init__(self, symbols: list[str] | None = None) -> None:
        self._symbols = symbols or ["FakeSymbol"]
        self.called_with: list[str] = []

    def extract(self, text: str) -> list[str]:
        self.called_with.append(text)
        return list(self._symbols)

    def filter_symbols(self, symbols: list[str], file_path: object) -> list[str]:
        # pass-through: no filtering in tests
        return list(symbols)


class FailingExtractor:
    def extract(self, text: str) -> list[str]:
        raise OllamaUnavailableError("ollama down")

    def filter_symbols(self, symbols: list[str], file_path: object) -> list[str]:
        raise OllamaUnavailableError("ollama down")


def make_chunker(chunks: list[Chunk]) -> Callable[[Path], list[Chunk]]:
    def chunker(path: Path) -> list[Chunk]:
        return chunks

    return chunker


def make_chunk(stem: str, index: int, text: str, source: str) -> Chunk:
    return Chunk(
        doc_id=f"{stem}__{index}",
        text=text,
        source_file=source,
        chunk_index=index,
    )


def make_watcher(
    paths: list[Path] | None = None,
    chunks: list[Chunk] | None = None,
    extractor: object | None = None,
) -> object:
    from src.indexer.watcher import Watcher

    source = "/fake/src/engine.py"
    default_chunks = [make_chunk("engine", 0, "def foo(): pass", source)]

    return Watcher(
        secrets_store=FakeSecretsStore(paths or []),
        vector_store=FakeVectorStore(),
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker(chunks or default_chunks),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=extractor or FakeExtractor(),  # type: ignore[arg-type]
    )


# --- construction -------------------------------------------------------------


def test_watcher_constructs_without_error() -> None:
    from src.indexer.watcher import Watcher

    watcher = Watcher(
        secrets_store=FakeSecretsStore([]),
        vector_store=FakeVectorStore(),
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker([]),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )

    assert watcher is not None


# --- index_path ---------------------------------------------------------------


def test_index_path_adds_chunks_to_vector_store(tmp_path: Path) -> None:
    from src.indexer.watcher import Watcher

    f = tmp_path / "engine.py"
    f.write_text("def foo(): pass", encoding="utf-8")
    chunks = [make_chunk("engine", 0, "def foo(): pass", str(f))]
    vs = FakeVectorStore()
    ss = FakeSymbolStore()

    watcher = Watcher(
        secrets_store=FakeSecretsStore([f]),
        vector_store=vs,
        symbol_store=ss,
        chunker=make_chunker(chunks),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )
    watcher.index_path(f)

    assert len(vs.added) == 1
    assert vs.added[0][0] == "engine__0"


def test_index_path_adds_all_chunks(tmp_path: Path) -> None:
    from src.indexer.watcher import Watcher

    f = tmp_path / "engine.py"
    f.write_text("content", encoding="utf-8")
    chunks = [
        make_chunk("engine", 0, "def foo(): pass", str(f)),
        make_chunk("engine", 1, "def bar(): pass", str(f)),
        make_chunk("engine", 2, "def baz(): pass", str(f)),
    ]
    vs = FakeVectorStore()

    watcher = Watcher(
        secrets_store=FakeSecretsStore([f]),
        vector_store=vs,
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker(chunks),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )
    watcher.index_path(f)

    assert len(vs.added) == 3


def test_index_path_stores_metadata_in_vector_store(tmp_path: Path) -> None:
    from src.indexer.watcher import Watcher

    f = tmp_path / "engine.py"
    f.write_text("content", encoding="utf-8")
    chunks = [make_chunk("engine", 0, "def foo(): pass", str(f))]
    vs = FakeVectorStore()

    watcher = Watcher(
        secrets_store=FakeSecretsStore([f]),
        vector_store=vs,
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker(chunks),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )
    watcher.index_path(f)

    _, _, meta = vs.added[0]
    assert "source_file" in meta
    assert str(f) in meta["source_file"]


def test_index_path_adds_symbols_to_symbol_store(tmp_path: Path) -> None:
    from src.indexer.watcher import Watcher

    f = tmp_path / "engine.py"
    f.write_text("class RiskScorer: pass", encoding="utf-8")
    chunks = [make_chunk("engine", 0, "class RiskScorer: pass", str(f))]
    ss = FakeSymbolStore()
    ext = FakeExtractor(symbols=["RiskScorer"])

    watcher = Watcher(
        secrets_store=FakeSecretsStore([f]),
        vector_store=FakeVectorStore(),
        symbol_store=ss,
        chunker=make_chunker(chunks),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=ext,  # type: ignore[arg-type]
    )
    watcher.index_path(f)

    assert len(ss.added) == 1
    source_file, symbols = ss.added[0]
    assert "RiskScorer" in symbols


def test_index_path_missing_file_logs_warning_and_does_not_raise(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from src.indexer.watcher import Watcher

    missing = tmp_path / "ghost.py"

    watcher = Watcher(
        secrets_store=FakeSecretsStore([missing]),
        vector_store=FakeVectorStore(),
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker([]),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.WARNING):
        watcher.index_path(missing)  # must not raise

    assert any("ghost.py" in r.message or "ghost" in r.message for r in caplog.records)


def test_index_path_ollama_unavailable_logs_warning_and_continues(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from src.indexer.watcher import Watcher

    f = tmp_path / "engine.py"
    f.write_text("class Foo: pass", encoding="utf-8")
    chunks = [make_chunk("engine", 0, "class Foo: pass", str(f))]
    vs = FakeVectorStore()

    watcher = Watcher(
        secrets_store=FakeSecretsStore([f]),
        vector_store=vs,
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker(chunks),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FailingExtractor(),  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.WARNING):
        watcher.index_path(f)  # must not raise

    # vector index was still populated
    assert len(vs.added) == 1
    assert any(
        "ollama" in r.message.lower() or "unavailable" in r.message.lower()
        for r in caplog.records
    )


def test_index_path_empty_file_adds_no_chunks(tmp_path: Path) -> None:
    from src.indexer.watcher import Watcher

    f = tmp_path / "empty.py"
    f.write_text("", encoding="utf-8")
    vs = FakeVectorStore()

    watcher = Watcher(
        secrets_store=FakeSecretsStore([f]),
        vector_store=vs,
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker([]),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )
    watcher.index_path(f)

    assert vs.added == []


# --- purge_path ---------------------------------------------------------------


def test_purge_path_deletes_from_vector_store(tmp_path: Path) -> None:
    from src.indexer.watcher import Watcher

    f = tmp_path / "engine.py"
    vs = FakeVectorStore()

    watcher = Watcher(
        secrets_store=FakeSecretsStore([]),
        vector_store=vs,
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker([]),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )
    watcher.purge_path(f)

    assert "engine" in vs.deleted


def test_purge_path_removes_from_symbol_store(tmp_path: Path) -> None:
    from src.indexer.watcher import Watcher

    f = tmp_path / "engine.py"
    ss = FakeSymbolStore()

    watcher = Watcher(
        secrets_store=FakeSecretsStore([]),
        vector_store=FakeVectorStore(),
        symbol_store=ss,
        chunker=make_chunker([]),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )
    watcher.purge_path(f)

    assert len(ss.removed) == 1


# --- start / stop -------------------------------------------------------------


def test_start_indexes_all_current_secrets_paths(tmp_path: Path) -> None:
    from src.indexer.watcher import Watcher

    f1 = tmp_path / "a.py"
    f2 = tmp_path / "b.py"
    f1.write_text("def a(): pass", encoding="utf-8")
    f2.write_text("def b(): pass", encoding="utf-8")
    secrets_path = tmp_path / "secrets"
    secrets_path.write_text("", encoding="utf-8")

    chunks_a = [make_chunk("a", 0, "def a(): pass", str(f1))]
    chunks_b = [make_chunk("b", 0, "def b(): pass", str(f2))]

    def chunker(path: Path) -> list[Chunk]:
        if path == f1:
            return chunks_a
        return chunks_b

    vs = FakeVectorStore()

    watcher = Watcher(
        secrets_store=FakeSecretsStore([f1, f2], secrets_path=secrets_path),
        vector_store=vs,
        symbol_store=FakeSymbolStore(),
        chunker=chunker,
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )
    watcher.start()
    watcher.stop()

    doc_ids = [doc_id for doc_id, _, _ in vs.added]
    assert "a__0" in doc_ids
    assert "b__0" in doc_ids


def test_stop_does_not_raise(tmp_path: Path) -> None:
    from src.indexer.watcher import Watcher

    secrets_path = tmp_path / "secrets"
    secrets_path.write_text("", encoding="utf-8")

    watcher = Watcher(
        secrets_store=FakeSecretsStore([], secrets_path=secrets_path),
        vector_store=FakeVectorStore(),
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker([]),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )
    watcher.start()
    watcher.stop()  # must not raise


def test_start_stop_idempotent(tmp_path: Path) -> None:
    from src.indexer.watcher import Watcher

    secrets_path = tmp_path / "secrets"
    secrets_path.write_text("", encoding="utf-8")

    watcher = Watcher(
        secrets_store=FakeSecretsStore([], secrets_path=secrets_path),
        vector_store=FakeVectorStore(),
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker([]),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )
    watcher.start()
    watcher.stop()
    watcher.stop()  # second stop must not raise


# --- observer selection -------------------------------------------------------


def test_is_docker_false_when_dockerenv_missing(tmp_path: Path) -> None:
    """_is_docker returns False on a normal host (/.dockerenv does not exist)."""
    from unittest.mock import patch

    from src.indexer.watcher import _is_docker

    with patch("src.indexer.watcher.Path") as mock_path_cls:
        # Simulate /.dockerenv not existing
        instance = mock_path_cls.return_value
        instance.exists.return_value = False
        assert _is_docker() is False


def test_is_docker_true_when_dockerenv_present(tmp_path: Path) -> None:
    """_is_docker returns True inside a Docker container (/.dockerenv exists)."""
    from unittest.mock import patch

    from src.indexer.watcher import _is_docker

    with patch("src.indexer.watcher.Path") as mock_path_cls:
        instance = mock_path_cls.return_value
        instance.exists.return_value = True
        assert _is_docker() is True


def test_start_uses_polling_observer_in_docker(tmp_path: Path) -> None:
    """Inside Docker, Watcher.start() must use PollingObserver, not Observer."""
    from unittest.mock import patch

    from watchdog.observers.polling import PollingObserver

    from src.indexer.watcher import Watcher

    secrets_path = tmp_path / "secrets"
    secrets_path.write_text("", encoding="utf-8")

    watcher = Watcher(
        secrets_store=FakeSecretsStore([], secrets_path=secrets_path),
        vector_store=FakeVectorStore(),
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker([]),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )

    with patch("src.indexer.watcher._is_docker", return_value=True):
        watcher.start()

    assert isinstance(watcher._observer, PollingObserver)
    watcher.stop()


def test_start_uses_native_observer_outside_docker(tmp_path: Path) -> None:
    """Outside Docker, Watcher.start() uses the native Observer."""
    from unittest.mock import patch

    from watchdog.observers import Observer

    from src.indexer.watcher import Watcher

    secrets_path = tmp_path / "secrets"
    secrets_path.write_text("", encoding="utf-8")

    watcher = Watcher(
        secrets_store=FakeSecretsStore([], secrets_path=secrets_path),
        vector_store=FakeVectorStore(),
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker([]),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )

    with patch("src.indexer.watcher._is_docker", return_value=False):
        watcher.start()

    assert isinstance(watcher._observer, Observer)
    watcher.stop()


# --- glob support ------------------------------------------------------------


def make_watcher_with_globs(
    tmp_path: Path,
    glob_rules: list[str],
    glob_expanded: dict[str, list[Path]],
    chunks: list[Chunk] | None = None,
) -> object:
    from src.indexer.watcher import Watcher

    secrets_path = tmp_path / "secrets"
    secrets_path.write_text("", encoding="utf-8")
    source = str(tmp_path / "engine.py")
    default_chunks = [make_chunk("engine", 0, "def foo(): pass", source)]

    return Watcher(
        secrets_store=FakeSecretsStore(
            paths=[],
            secrets_path=secrets_path,
            glob_rules=glob_rules,
            glob_expanded=glob_expanded,
        ),
        vector_store=FakeVectorStore(),
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker(chunks or default_chunks),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )


def test_initial_scan_indexes_files_from_glob_rules(tmp_path: Path) -> None:
    """initial_scan must expand glob rules and index each matched file."""
    from src.indexer.watcher import Watcher

    f = tmp_path / "scorer.py"
    f.write_text("def score(): pass", encoding="utf-8")
    source = str(f)
    chunks = [make_chunk("scorer", 0, "def score(): pass", source)]

    secrets_path = tmp_path / "secrets"
    secrets_path.write_text("", encoding="utf-8")

    vs = FakeVectorStore()
    ss_store = FakeSecretsStore(
        paths=[],
        secrets_path=secrets_path,
        glob_rules=["src/"],
        glob_expanded={"src/": [f]},
    )

    watcher = Watcher(
        secrets_store=ss_store,
        vector_store=vs,
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker(chunks),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )

    watcher.initial_scan()

    assert vs.count_prefix("scorer") == 1


def test_initial_scan_skips_already_indexed_glob_files(tmp_path: Path) -> None:
    """Files already in the vector store must not be re-indexed during initial_scan."""
    from src.indexer.watcher import Watcher

    f = tmp_path / "scorer.py"
    f.write_text("def score(): pass", encoding="utf-8")
    source = str(f)
    chunks = [make_chunk("scorer", 0, "def score(): pass", source)]

    secrets_path = tmp_path / "secrets"
    secrets_path.write_text("", encoding="utf-8")

    vs = FakeVectorStore()
    # Pre-populate vector store so the file appears already indexed
    vs.add("scorer__0", [1.0, 2.0], {"source_file": source, "chunk_index": "0"})

    ss_store = FakeSecretsStore(
        paths=[],
        secrets_path=secrets_path,
        glob_rules=["src/"],
        glob_expanded={"src/": [f]},
    )

    watcher = Watcher(
        secrets_store=ss_store,
        vector_store=vs,
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker(chunks),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )

    watcher.initial_scan()

    assert vs.count_prefix("scorer") == 1  # still 1, not 2


def test_rescan_globs_indexes_new_files(tmp_path: Path) -> None:
    """_rescan_globs must index files that appeared after initial_scan."""
    from src.indexer.watcher import Watcher

    new_file = tmp_path / "new_scorer.py"
    new_file.write_text("def score(): pass", encoding="utf-8")
    source = str(new_file)
    chunks = [make_chunk("new_scorer", 0, "def score(): pass", source)]

    secrets_path = tmp_path / "secrets"
    secrets_path.write_text("", encoding="utf-8")

    vs = FakeVectorStore()
    ss_store = FakeSecretsStore(
        paths=[],
        secrets_path=secrets_path,
        glob_rules=["src/"],
        glob_expanded={"src/": []},  # empty initially
    )

    watcher = Watcher(
        secrets_store=ss_store,
        vector_store=vs,
        symbol_store=FakeSymbolStore(),
        chunker=make_chunker(chunks),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )
    watcher._known_glob_rules = {"src/"}
    watcher._glob_expanded = {"src/": set()}

    # Simulate new file appearing: update the fake store's expansion
    ss_store._glob_expanded["src/"] = [new_file]

    watcher._rescan_globs()

    assert vs.count_prefix("new_scorer") == 1


def test_rescan_globs_purges_removed_files(tmp_path: Path) -> None:
    """_rescan_globs must purge files that disappeared from the glob expansion."""
    from src.indexer.watcher import Watcher

    gone_file = tmp_path / "gone.py"
    # Do NOT create the file — it's been deleted

    secrets_path = tmp_path / "secrets"
    secrets_path.write_text("", encoding="utf-8")

    vs = FakeVectorStore()
    sym = FakeSymbolStore()
    ss_store = FakeSecretsStore(
        paths=[],
        secrets_path=secrets_path,
        glob_rules=["src/"],
        glob_expanded={"src/": []},  # now empty (file was removed)
    )

    watcher = Watcher(
        secrets_store=ss_store,
        vector_store=vs,
        symbol_store=sym,
        chunker=make_chunker([]),
        embedder=FakeEmbedder(),  # type: ignore[arg-type]
        extractor=FakeExtractor(),  # type: ignore[arg-type]
    )
    watcher._known_glob_rules = {"src/"}
    watcher._glob_expanded = {"src/": {gone_file}}  # was indexed

    watcher._rescan_globs()

    assert "gone" in vs.deleted
    assert str(gone_file) in sym.removed
