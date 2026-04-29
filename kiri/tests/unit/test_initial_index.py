"""
Tests for US-10: initial_scan() and gateway index --all.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.config.settings import Settings
from src.indexer.watcher import Watcher
from src.store.secrets_store import SecretsStore
from src.store.symbol_store import SymbolStore
from src.store.vector_store import VectorStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_watcher(
    tmp_path: Path,
    paths: list[Path],
    already_indexed: set[str] | None = None,
) -> tuple[Watcher, MagicMock]:
    """Build a Watcher with fake stores and spy on index_path calls."""
    secrets_path = tmp_path / ".kiri" / "secrets"
    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    lines = "\n".join(str(p) for p in paths)
    secrets_path.write_text(lines, encoding="utf-8")

    vs = MagicMock(spec=VectorStore)
    already = already_indexed or set()
    vs.count_prefix.side_effect = lambda stem: 1 if stem in already else 0

    ss = MagicMock(spec=SymbolStore)
    secrets_store = SecretsStore(secrets_path=secrets_path, workspace=tmp_path)

    watcher = Watcher(
        secrets_store=secrets_store,
        vector_store=vs,
        symbol_store=ss,
        chunker=MagicMock(return_value=[]),
        embedder=MagicMock(),
        extractor=MagicMock(),
        settings=Settings(workspace=tmp_path),
    )
    return watcher, vs


# ---------------------------------------------------------------------------
# VectorStore.count_prefix
# ---------------------------------------------------------------------------

class TestCountPrefix:

    def test_count_prefix_zero_when_empty(self, tmp_path: Path):
        from src.store.vector_store import VectorStore
        vs = VectorStore(index_dir=tmp_path / "index")
        assert vs.count_prefix("scorer") == 0

    def test_count_prefix_after_add(self, tmp_path: Path):
        from src.store.vector_store import VectorStore
        vs = VectorStore(index_dir=tmp_path / "index")
        vs.add("scorer__0", [0.1] * 384, {"source_file": "scorer.py", "chunk_index": "0"})
        vs.add("scorer__1", [0.2] * 384, {"source_file": "scorer.py", "chunk_index": "1"})
        assert vs.count_prefix("scorer") == 2

    def test_count_prefix_does_not_count_other_stems(self, tmp_path: Path):
        from src.store.vector_store import VectorStore
        vs = VectorStore(index_dir=tmp_path / "index")
        vs.add("scorer__0", [0.1] * 384, {"source_file": "scorer.py", "chunk_index": "0"})
        vs.add("calibrator__0", [0.2] * 384, {"source_file": "calibrator.py", "chunk_index": "0"})
        assert vs.count_prefix("scorer") == 1
        assert vs.count_prefix("calibrator") == 1

    def test_count_prefix_partial_name_does_not_match(self, tmp_path: Path):
        from src.store.vector_store import VectorStore
        vs = VectorStore(index_dir=tmp_path / "index")
        vs.add("risk_scorer__0", [0.1] * 384, {"source_file": "risk_scorer.py", "chunk_index": "0"})
        assert vs.count_prefix("scorer") == 0
        assert vs.count_prefix("risk_scorer") == 1


# ---------------------------------------------------------------------------
# Watcher.initial_scan
# ---------------------------------------------------------------------------

class TestInitialScan:

    def test_indexes_file_not_yet_in_store(self, tmp_path: Path):
        f = tmp_path / "engine.py"
        f.write_text("x = 1", encoding="utf-8")
        watcher, vs = _make_watcher(tmp_path, [f], already_indexed=set())

        with patch.object(watcher, "index_path") as mock_index:
            watcher.initial_scan()

        mock_index.assert_called_once_with(f)

    def test_skips_file_already_indexed(self, tmp_path: Path):
        f = tmp_path / "engine.py"
        f.write_text("x = 1", encoding="utf-8")
        watcher, vs = _make_watcher(tmp_path, [f], already_indexed={"engine"})

        with patch.object(watcher, "index_path") as mock_index:
            watcher.initial_scan()

        mock_index.assert_not_called()

    def test_skips_missing_file_without_crash(self, tmp_path: Path):
        missing = tmp_path / "ghost.py"  # does not exist
        watcher, vs = _make_watcher(tmp_path, [missing], already_indexed=set())

        with patch.object(watcher, "index_path") as mock_index:
            watcher.initial_scan()  # must not raise

        mock_index.assert_not_called()

    def test_indexes_only_unindexed_files(self, tmp_path: Path):
        f1 = tmp_path / "scorer.py"
        f2 = tmp_path / "calibrator.py"
        f1.write_text("x = 1", encoding="utf-8")
        f2.write_text("y = 2", encoding="utf-8")
        watcher, vs = _make_watcher(tmp_path, [f1, f2], already_indexed={"scorer"})

        with patch.object(watcher, "index_path") as mock_index:
            watcher.initial_scan()

        mock_index.assert_called_once_with(f2)

    def test_empty_secrets_scans_nothing(self, tmp_path: Path):
        watcher, vs = _make_watcher(tmp_path, [], already_indexed=set())

        with patch.object(watcher, "index_path") as mock_index:
            watcher.initial_scan()

        mock_index.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_index.run_all
# ---------------------------------------------------------------------------

class TestRunAll:

    def test_run_all_returns_done(self, tmp_path: Path):
        from src.cli.commands.index import run_all

        secrets_path = tmp_path / ".kiri" / "secrets"
        secrets_path.parent.mkdir(parents=True, exist_ok=True)
        secrets_path.write_text("", encoding="utf-8")

        result = run_all(Settings(workspace=tmp_path))
        assert "nothing to index" in result.lower() or "done" in result.lower()

    def test_run_all_reports_missing_file(self, tmp_path: Path):
        from src.cli.commands.index import run_all

        secrets_path = tmp_path / ".kiri" / "secrets"
        secrets_path.parent.mkdir(parents=True, exist_ok=True)
        secrets_path.write_text(str(tmp_path / "ghost.py"), encoding="utf-8")

        result = run_all(Settings(workspace=tmp_path))
        assert "ghost.py" in result
        assert "not found" in result.lower() or "!" in result
