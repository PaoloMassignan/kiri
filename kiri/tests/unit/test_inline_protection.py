"""
TDD tests for sub-file and inline protection features (US-1, US-2, US-3).

Covers:
  - SecretsStore: parsing of path::symbol and @inline blocks
  - SecretsStore: read/write API for sub-file entries and inline blocks
  - Watcher: indexes only the named function chunk (US-1)
  - Watcher: indexes inline block content (US-2)
  - SymbolStore: @symbol with value registers both name and numeric constant (US-3)
  - Pipeline: integration — sub-file and inline blocks protect correctly
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_secrets_store(tmp_path: Path, content: str = ""):
    from src.store.secrets_store import SecretsStore
    workspace = tmp_path / "project"
    workspace.mkdir(exist_ok=True)
    gw = workspace / ".kiri"
    gw.mkdir(exist_ok=True)
    secrets = gw / "secrets"
    secrets.write_text(content, encoding="utf-8")
    return SecretsStore(secrets_path=secrets, workspace=workspace)


# ===========================================================================
# US-1 — Sub-file granularity: path::symbol syntax
# ===========================================================================


class TestSecretsStoreSubFile:

    def test_parses_subfile_entry(self, tmp_path):
        store = make_secrets_store(
            tmp_path,
            "creditscorer/core/scorer.py::_weighted_sum\n"
        )
        entries = store.list_subfile_entries()
        assert len(entries) == 1
        assert entries[0].path.name == "scorer.py"
        assert entries[0].symbol == "_weighted_sum"

    def test_parses_multiple_subfile_entries_same_file(self, tmp_path):
        store = make_secrets_store(
            tmp_path,
            "creditscorer/core/scorer.py::_weighted_sum\n"
            "creditscorer/core/scorer.py::_score_utilization\n"
        )
        entries = store.list_subfile_entries()
        symbols = [e.symbol for e in entries]
        assert "_weighted_sum" in symbols
        assert "_score_utilization" in symbols

    def test_subfile_entry_does_not_appear_in_list_paths(self, tmp_path):
        store = make_secrets_store(
            tmp_path,
            "creditscorer/core/scorer.py::_weighted_sum\n"
        )
        assert store.list_paths() == []

    def test_full_file_and_subfile_coexist(self, tmp_path):
        project = tmp_path / "project"
        (project / "creditscorer" / "core").mkdir(parents=True)
        (project / "creditscorer" / "core" / "scorer.py").touch()
        (project / "creditscorer" / "core" / "calibrator.py").touch()

        store = make_secrets_store(
            tmp_path,
            "creditscorer/core/calibrator.py\n"
            "creditscorer/core/scorer.py::_weighted_sum\n"
        )
        paths = store.list_paths()
        entries = store.list_subfile_entries()
        assert len(paths) == 1
        assert paths[0].name == "calibrator.py"
        assert len(entries) == 1
        assert entries[0].symbol == "_weighted_sum"

    def test_add_subfile_entry(self, tmp_path):
        project = tmp_path / "project"
        (project / "src").mkdir(parents=True)
        target = project / "src" / "scorer.py"
        target.touch()
        store = make_secrets_store(tmp_path)

        store.add_subfile(target, "_weighted_sum")

        entries = store.list_subfile_entries()
        assert any(e.symbol == "_weighted_sum" for e in entries)

    def test_add_subfile_entry_is_idempotent(self, tmp_path):
        project = tmp_path / "project"
        (project / "src").mkdir(parents=True)
        target = project / "src" / "scorer.py"
        target.touch()
        store = make_secrets_store(tmp_path)

        store.add_subfile(target, "_weighted_sum")
        store.add_subfile(target, "_weighted_sum")

        entries = [e for e in store.list_subfile_entries() if e.symbol == "_weighted_sum"]
        assert len(entries) == 1

    def test_remove_subfile_entry(self, tmp_path):
        project = tmp_path / "project"
        (project / "src").mkdir(parents=True)
        target = project / "src" / "scorer.py"
        target.touch()
        store = make_secrets_store(tmp_path)
        store.add_subfile(target, "_weighted_sum")

        store.remove_subfile(target, "_weighted_sum")

        entries = store.list_subfile_entries()
        assert not any(e.symbol == "_weighted_sum" for e in entries)

    def test_remove_nonexistent_subfile_does_not_raise(self, tmp_path):
        store = make_secrets_store(tmp_path)
        ghost = tmp_path / "project" / "ghost.py"
        store.remove_subfile(ghost, "_foo")  # must not raise


# ===========================================================================
# US-2 — Inline blocks: @inline / @end syntax
# ===========================================================================


class TestSecretsStoreInline:

    def test_parses_single_inline_block(self, tmp_path):
        store = make_secrets_store(
            tmp_path,
            "@inline platt_params\n"
            "_A = -3.2174\n"
            "_B =  1.8831\n"
            "@end\n"
        )
        blocks = store.list_inline_blocks()
        assert len(blocks) == 1
        assert blocks[0].name == "platt_params"
        assert "_A = -3.2174" in blocks[0].content

    def test_parses_multiple_inline_blocks(self, tmp_path):
        store = make_secrets_store(
            tmp_path,
            "@inline block_a\n"
            "foo = 1\n"
            "@end\n"
            "@inline block_b\n"
            "bar = 2\n"
            "@end\n"
        )
        blocks = store.list_inline_blocks()
        assert len(blocks) == 2
        names = [b.name for b in blocks]
        assert "block_a" in names
        assert "block_b" in names

    def test_inline_block_does_not_appear_in_list_paths(self, tmp_path):
        store = make_secrets_store(
            tmp_path,
            "@inline platt_params\n"
            "_A = -3.2174\n"
            "@end\n"
        )
        assert store.list_paths() == []

    def test_inline_block_does_not_appear_in_list_symbols(self, tmp_path):
        store = make_secrets_store(
            tmp_path,
            "@inline platt_params\n"
            "_A = -3.2174\n"
            "@end\n"
        )
        assert store.list_symbols() == []

    def test_inline_block_coexists_with_paths_and_symbols(self, tmp_path):
        project = tmp_path / "project"
        (project / "src").mkdir(parents=True)
        (project / "src" / "scorer.py").touch()
        store = make_secrets_store(
            tmp_path,
            "src/scorer.py\n"
            "@symbol MySymbol\n"
            "@inline platt_params\n"
            "_A = -3.2174\n"
            "@end\n"
        )
        assert len(store.list_paths()) == 1
        assert "MySymbol" in store.list_symbols()
        assert len(store.list_inline_blocks()) == 1

    def test_add_inline_block(self, tmp_path):
        store = make_secrets_store(tmp_path)

        store.add_inline_block("fraud_model", "_THRESHOLD = 0.847\n_CUTOFF = 0.5\n")

        blocks = store.list_inline_blocks()
        assert len(blocks) == 1
        assert blocks[0].name == "fraud_model"
        assert "_THRESHOLD = 0.847" in blocks[0].content

    def test_add_inline_block_is_idempotent_by_name(self, tmp_path):
        store = make_secrets_store(tmp_path)
        store.add_inline_block("fraud_model", "_THRESHOLD = 0.847\n")
        store.add_inline_block("fraud_model", "_THRESHOLD = 0.847\n")

        blocks = [b for b in store.list_inline_blocks() if b.name == "fraud_model"]
        assert len(blocks) == 1

    def test_remove_inline_block(self, tmp_path):
        store = make_secrets_store(tmp_path)
        store.add_inline_block("fraud_model", "_THRESHOLD = 0.847\n")

        store.remove_inline_block("fraud_model")

        assert not any(b.name == "fraud_model" for b in store.list_inline_blocks())

    def test_remove_nonexistent_inline_block_does_not_raise(self, tmp_path):
        store = make_secrets_store(tmp_path)
        store.remove_inline_block("ghost")  # must not raise

    def test_inline_block_content_preserved_across_write(self, tmp_path):
        store = make_secrets_store(tmp_path)
        content = "_A = -3.2174\n_B =  1.8831\n"
        store.add_inline_block("platt", content)

        # reload from disk
        from src.store.secrets_store import SecretsStore
        store2 = SecretsStore(
            secrets_path=store.secrets_path,
            workspace=store.workspace,
        )
        blocks = store2.list_inline_blocks()
        assert blocks[0].content.strip() == content.strip()

    def test_inline_block_content_is_multiline(self, tmp_path):
        multiline = (
            "# Fitted on Q3 2024 dataset\n"
            "_A = -3.2174\n"
            "_B =  1.8831\n"
        )
        store = make_secrets_store(tmp_path)
        store.add_inline_block("platt", multiline)

        blocks = store.list_inline_blocks()
        assert "# Fitted on Q3 2024 dataset" in blocks[0].content
        assert "_A = -3.2174" in blocks[0].content
        assert "_B =  1.8831" in blocks[0].content


# ===========================================================================
# US-3 — @symbol with value
# ===========================================================================


class TestSecretsStoreSymbolWithValue:

    def test_parses_symbol_with_float_value(self, tmp_path):
        store = make_secrets_store(
            tmp_path,
            "@symbol FRAUD_SCORE_THRESHOLD = 0.847\n"
        )
        valued = store.list_valued_symbols()
        assert len(valued) == 1
        assert valued[0].name == "FRAUD_SCORE_THRESHOLD"
        assert abs(valued[0].value - 0.847) < 1e-9

    def test_parses_symbol_with_integer_value(self, tmp_path):
        store = make_secrets_store(
            tmp_path,
            "@symbol MAX_EXPOSURE_LIMIT = 2500000\n"
        )
        valued = store.list_valued_symbols()
        assert valued[0].name == "MAX_EXPOSURE_LIMIT"
        assert valued[0].value == 2500000.0

    def test_plain_symbol_not_in_valued_list(self, tmp_path):
        store = make_secrets_store(
            tmp_path,
            "@symbol RiskScorer\n"
            "@symbol FRAUD_SCORE_THRESHOLD = 0.847\n"
        )
        valued = store.list_valued_symbols()
        assert len(valued) == 1
        assert valued[0].name == "FRAUD_SCORE_THRESHOLD"

    def test_valued_symbol_also_appears_in_list_symbols(self, tmp_path):
        store = make_secrets_store(
            tmp_path,
            "@symbol FRAUD_SCORE_THRESHOLD = 0.847\n"
        )
        assert "FRAUD_SCORE_THRESHOLD" in store.list_symbols()

    def test_add_valued_symbol(self, tmp_path):
        store = make_secrets_store(tmp_path)
        store.add_valued_symbol("FRAUD_SCORE_THRESHOLD", 0.847)

        valued = store.list_valued_symbols()
        assert any(v.name == "FRAUD_SCORE_THRESHOLD" for v in valued)

    def test_add_valued_symbol_is_idempotent(self, tmp_path):
        store = make_secrets_store(tmp_path)
        store.add_valued_symbol("FRAUD_SCORE_THRESHOLD", 0.847)
        store.add_valued_symbol("FRAUD_SCORE_THRESHOLD", 0.847)

        valued = [v for v in store.list_valued_symbols() if v.name == "FRAUD_SCORE_THRESHOLD"]
        assert len(valued) == 1


# ===========================================================================
# Watcher integration — sub-file indexing
# ===========================================================================


class TestWatcherSubFile:

    def _make_pipeline_deps(self, tmp_path):
        from src.config.settings import Settings
        from src.indexer.embedder import Embedder
        from src.store.symbol_store import SymbolStore
        from src.store.vector_store import VectorStore

        settings = Settings()
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        return (
            settings,
            Embedder(settings),
            VectorStore(index_dir),
            SymbolStore(index_dir),
        )

    def test_subfile_indexes_only_named_function_chunk(self, tmp_path):
        """
        When a path::symbol entry is indexed, only the chunk for that
        function enters the vector store — not the rest of the file.
        """
        from src.indexer.watcher import Watcher
        from src.store.secrets_store import SecretsStore

        _settings, embedder, vs, ss = self._make_pipeline_deps(tmp_path)

        scorer = tmp_path / "scorer.py"
        scorer.write_text(
            "def _weighted_sum(components): return sum(components.values())\n\n"
            "def _scale(raw): return round(300 + raw * 550)\n",
            encoding="utf-8",
        )

        secrets_file = tmp_path / "secrets"
        secrets_file.write_text("", encoding="utf-8")
        store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)
        store.add_subfile(scorer, "_weighted_sum")

        extractor_mock = MagicMock()
        extractor_mock.extract.return_value = []
        from src.indexer.chunker import chunk
        watcher = Watcher(
            secrets_store=store,
            vector_store=vs,
            symbol_store=ss,
            chunker=chunk,
            embedder=embedder,
            extractor=extractor_mock,
        )
        watcher.index_subfile(scorer, "_weighted_sum")

        # Only _weighted_sum chunk should be indexed
        assert vs.count() == 1
        # _scale should not be indexed — the one chunk is about _weighted_sum
        results = vs.query(embedder.embed(["def _scale(raw)"])[0], top_k=5)
        assert all(r.similarity < 0.95 for r in results)

    def test_subfile_registers_symbol_in_l2(self, tmp_path):
        """
        index_subfile must register the function name in the symbol store.
        """
        from src.indexer.watcher import Watcher
        from src.store.secrets_store import SecretsStore

        _settings, embedder, vs, ss = self._make_pipeline_deps(tmp_path)

        scorer = tmp_path / "scorer.py"
        scorer.write_text(
            "def _weighted_sum(components): return sum(components.values())\n",
            encoding="utf-8",
        )
        secrets_file = tmp_path / "secrets"
        secrets_file.write_text("", encoding="utf-8")
        store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

        extractor_mock = MagicMock()
        extractor_mock.extract.return_value = []
        from src.indexer.chunker import chunk
        watcher = Watcher(
            secrets_store=store,
            vector_store=vs,
            symbol_store=ss,
            chunker=chunk,
            embedder=embedder,
            extractor=extractor_mock,
        )
        watcher.index_subfile(scorer, "_weighted_sum")

        assert "_weighted_sum" in ss.all_symbols()


# ===========================================================================
# Watcher integration — inline block indexing
# ===========================================================================


class TestWatcherInline:

    def _make_deps(self, tmp_path):
        from src.config.settings import Settings
        from src.indexer.embedder import Embedder
        from src.store.symbol_store import SymbolStore
        from src.store.vector_store import VectorStore

        settings = Settings()
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        return (
            Embedder(settings),
            VectorStore(index_dir),
            SymbolStore(index_dir),
        )

    def test_inline_block_is_indexed_in_vector_store(self, tmp_path):
        from src.indexer.watcher import Watcher
        from src.store.secrets_store import InlineBlock, SecretsStore

        embedder, vs, ss = self._make_deps(tmp_path)
        secrets_file = tmp_path / "secrets"
        secrets_file.write_text("", encoding="utf-8")
        store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

        extractor_mock = MagicMock()
        extractor_mock.extract.return_value = []
        from src.indexer.chunker import chunk
        watcher = Watcher(
            secrets_store=store,
            vector_store=vs,
            symbol_store=ss,
            chunker=chunk,
            embedder=embedder,
            extractor=extractor_mock,
        )

        block = InlineBlock(name="platt", content="_A = -3.2174\n_B = 1.8831\n")
        watcher.index_inline_block(block)

        assert vs.count() == 1

    def test_inline_block_symbols_registered_in_l2(self, tmp_path):
        from src.indexer.watcher import Watcher
        from src.store.secrets_store import InlineBlock, SecretsStore

        embedder, vs, ss = self._make_deps(tmp_path)
        secrets_file = tmp_path / "secrets"
        secrets_file.write_text("", encoding="utf-8")
        store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

        extractor_mock = MagicMock()
        extractor_mock.extract.return_value = []
        from src.indexer.chunker import chunk
        watcher = Watcher(
            secrets_store=store,
            vector_store=vs,
            symbol_store=ss,
            chunker=chunk,
            embedder=embedder,
            extractor=extractor_mock,
        )

        block = InlineBlock(name="platt", content="_A = -3.2174\n_B = 1.8831\n")
        watcher.index_inline_block(block)

        # _A and _B are private symbols — should be in L2
        symbols = ss.all_symbols()
        assert "_A" in symbols or "_B" in symbols

    def test_inline_block_numeric_constants_registered(self, tmp_path):
        from src.indexer.watcher import Watcher
        from src.store.secrets_store import InlineBlock, SecretsStore

        embedder, vs, ss = self._make_deps(tmp_path)
        secrets_file = tmp_path / "secrets"
        secrets_file.write_text("", encoding="utf-8")
        store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

        extractor_mock = MagicMock()
        extractor_mock.extract.return_value = []
        from src.indexer.chunker import chunk
        watcher = Watcher(
            secrets_store=store,
            vector_store=vs,
            symbol_store=ss,
            chunker=chunk,
            embedder=embedder,
            extractor=extractor_mock,
        )

        block = InlineBlock(name="platt", content="_A = -3.2174\n_B = 1.8831\n")
        watcher.index_inline_block(block)

        numbers = [v for v, _ in ss.all_numbers()]
        assert any(abs(n - (-3.2174)) < 1e-4 for n in numbers)
        assert any(abs(n - 1.8831) < 1e-4 for n in numbers)


# ===========================================================================
# US-3 — Valued symbols feed both L2 and numeric store on startup
# ===========================================================================


class TestValuedSymbolsIntegration:

    def test_valued_symbol_enters_l2_and_numeric_store(self, tmp_path):
        """
        When the gateway starts and finds @symbol FOO = 1.23 in secrets,
        it must register FOO in the symbol store (L2) AND 1.23 in the
        numeric constants store.
        """
        from src.store.secrets_store import SecretsStore
        from src.store.symbol_store import SymbolStore

        ss = SymbolStore(tmp_path)
        secrets_file = tmp_path / "secrets"
        secrets_file.write_text(
            "@symbol FRAUD_SCORE_THRESHOLD = 0.847\n",
            encoding="utf-8",
        )
        store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

        # Simulate what the startup routine does with valued symbols
        for vs in store.list_valued_symbols():
            ss.add_explicit([vs.name])
            ss.add_numbers("@explicit", [(vs.value, _sig_figs(str(vs.value)))])

        assert "FRAUD_SCORE_THRESHOLD" in ss.all_symbols()
        numbers = [v for v, _ in ss.all_numbers()]
        assert any(abs(n - 0.847) < 1e-4 for n in numbers)


def _sig_figs(s: str) -> int:
    """Minimal sig figs helper for the integration test above."""
    digits = s.lstrip("+-").replace(".", "").lstrip("0")
    return len(digits) if digits else 1
