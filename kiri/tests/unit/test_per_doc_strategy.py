"""
TDD — per-document strategy (US-S1 … US-S5).

La strategy (BLOCK/REDACT) viene determinata dal documento sorgente del match,
non da un flag globale al costruttore del FilterPipeline.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ===========================================================================
# US-S1/S2/S3 — SecretsStore.get_strategy_for_source()
# ===========================================================================


class TestSecretsStoreStrategyForSource:
    """get_strategy_for_source(key) risolve la strategy per qualsiasi tipo di sorgente."""

    def _store(self, tmp_path: Path, content: str):
        from src.store.secrets_store import SecretsStore

        secrets = tmp_path / "secrets"
        secrets.write_text(content, encoding="utf-8")
        workspace = tmp_path
        return SecretsStore(secrets_path=secrets, workspace=workspace)

    # --- file path -----------------------------------------------------------

    def test_file_path_default_is_block(self, tmp_path):
        from src.store.secrets_store import ProtectionStrategy

        (tmp_path / "scorer.py").touch()
        store = self._store(tmp_path, "scorer.py\n")
        assert store.get_strategy_for_source("scorer.py") == ProtectionStrategy.BLOCK

    def test_file_path_redact_annotation(self, tmp_path):
        from src.store.secrets_store import ProtectionStrategy

        (tmp_path / "scorer.py").touch()
        store = self._store(tmp_path, "scorer.py [strategy=redact]\n")
        assert store.get_strategy_for_source("scorer.py") == ProtectionStrategy.REDACT

    def test_file_path_unknown_source_returns_block(self, tmp_path):
        from src.store.secrets_store import ProtectionStrategy

        store = self._store(tmp_path, "")
        assert store.get_strategy_for_source("nonexistent.py") == ProtectionStrategy.BLOCK

    # --- inline block --------------------------------------------------------

    def test_inline_block_default_is_block(self, tmp_path):
        from src.store.secrets_store import ProtectionStrategy

        store = self._store(tmp_path, "@inline my_algo\ndef my_algo(): pass\n@end\n")
        assert store.get_strategy_for_source("@inline:my_algo") == ProtectionStrategy.BLOCK

    def test_inline_block_redact_annotation(self, tmp_path):
        from src.store.secrets_store import ProtectionStrategy

        store = self._store(
            tmp_path,
            "@inline my_algo [strategy=redact]\ndef my_algo(): pass\n@end\n",
        )
        assert store.get_strategy_for_source("@inline:my_algo") == ProtectionStrategy.REDACT

    def test_inline_block_unknown_name_returns_block(self, tmp_path):
        from src.store.secrets_store import ProtectionStrategy

        store = self._store(tmp_path, "")
        assert store.get_strategy_for_source("@inline:missing") == ProtectionStrategy.BLOCK

    # --- sub-file (path::symbol) --------------------------------------------

    def test_subfile_default_is_block(self, tmp_path):
        from src.store.secrets_store import ProtectionStrategy

        (tmp_path / "scorer.py").touch()
        store = self._store(tmp_path, "scorer.py::_weighted_sum\n")
        assert (
            store.get_strategy_for_source("scorer.py::_weighted_sum") == ProtectionStrategy.BLOCK
        )

    def test_subfile_redact_annotation(self, tmp_path):
        from src.store.secrets_store import ProtectionStrategy

        (tmp_path / "scorer.py").touch()
        store = self._store(tmp_path, "scorer.py::_weighted_sum [strategy=redact]\n")
        assert (
            store.get_strategy_for_source("scorer.py::_weighted_sum") == ProtectionStrategy.REDACT
        )

    def test_subfile_redact_does_not_affect_other_symbols(self, tmp_path):
        from src.store.secrets_store import ProtectionStrategy

        (tmp_path / "scorer.py").touch()
        store = self._store(
            tmp_path,
            "scorer.py::_weighted_sum [strategy=redact]\nscorer.py::_scale\n",
        )
        assert (
            store.get_strategy_for_source("scorer.py::_scale") == ProtectionStrategy.BLOCK
        )


# ===========================================================================
# SymbolStore — scan_with_source()
# ===========================================================================


class TestSymbolStoreScanWithSource:
    """scan_with_source() ritorna (symbol, source_file) per ogni match."""

    def test_returns_source_file_with_symbol(self, tmp_path):
        from src.store.symbol_store import SymbolStore

        ss = SymbolStore(tmp_path)
        ss.add("src/scorer.py", ["_weighted_sum"])
        results = ss.scan_with_source("call _weighted_sum here")
        assert len(results) == 1
        symbol, source = results[0]
        assert symbol == "_weighted_sum"
        assert source == "src/scorer.py"

    def test_multiple_symbols_from_different_sources(self, tmp_path):
        from src.store.symbol_store import SymbolStore

        ss = SymbolStore(tmp_path)
        ss.add("src/a.py", ["_foo"])
        ss.add("src/b.py", ["_bar"])
        results = ss.scan_with_source("call _foo and _bar")
        sources = dict(results)
        assert sources["_foo"] == "src/a.py"
        assert sources["_bar"] == "src/b.py"

    def test_no_match_returns_empty(self, tmp_path):
        from src.store.symbol_store import SymbolStore

        ss = SymbolStore(tmp_path)
        ss.add("src/scorer.py", ["_weighted_sum"])
        assert ss.scan_with_source("nothing relevant") == []

    def test_numeric_match_includes_source(self, tmp_path):
        from src.store.symbol_store import SymbolStore

        ss = SymbolStore(tmp_path)
        ss.add_numbers("src/scorer.py", [(0.1233, 4)])
        results = ss.scan_with_source("weight is 0.1233")
        assert len(results) == 1
        _, source = results[0]
        assert source == "src/scorer.py"


# ===========================================================================
# L2Filter — matched_with_source
# ===========================================================================


class TestL2FilterWithSource:
    """L2Result espone matched_with_source: list[tuple[str, str]]."""

    def test_l2_result_has_matched_with_source(self, tmp_path):
        from src.filter.l2_symbols import L2Filter
        from src.store.symbol_store import SymbolStore

        ss = SymbolStore(tmp_path)
        ss.add("src/scorer.py", ["_weighted_sum"])
        l2 = L2Filter(ss)
        result = l2.check("def _weighted_sum(): ...")
        assert hasattr(result, "matched_with_source")
        assert ("_weighted_sum", "src/scorer.py") in result.matched_with_source

    def test_l2_result_matched_still_works(self, tmp_path):
        """matched (list[str]) rimane per backward compat."""
        from src.filter.l2_symbols import L2Filter
        from src.store.symbol_store import SymbolStore

        ss = SymbolStore(tmp_path)
        ss.add("src/scorer.py", ["_weighted_sum"])
        l2 = L2Filter(ss)
        result = l2.check("def _weighted_sum(): ...")
        assert "_weighted_sum" in result.matched


# ===========================================================================
# FilterPipeline — per-document strategy
# ===========================================================================


class TestPipelinePerDocStrategy:
    """Il pipeline risolve la strategy dal documento sorgente del match."""

    def _make_pipeline(
        self,
        secrets_content: str,
        tmp_path: Path,
        l2_matched_with_source=None,
        l1_score: float = 0.5,
        l1_source_file: str = "",
        l3_is_leak: bool = True,
    ):
        from src.config.settings import Settings
        from src.filter.l3_classifier import L3Result
        from src.filter.pipeline import FilterPipeline
        from src.store.secrets_store import SecretsStore

        secrets_file = tmp_path / "secrets"
        secrets_file.write_text(secrets_content, encoding="utf-8")
        secrets_store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

        l1 = MagicMock()
        l1.check.return_value = MagicMock(
            top_score=l1_score, top_source_file=l1_source_file
        )

        l2 = MagicMock()
        l2_result = MagicMock()
        l2_result.matched = [s for s, _ in (l2_matched_with_source or [])]
        l2_result.matched_with_source = l2_matched_with_source or []
        l2.check.return_value = l2_result

        l3 = MagicMock()
        l3.check.return_value = L3Result(is_leak=l3_is_leak)

        settings = Settings()
        return FilterPipeline(l1=l1, l2=l2, l3=l3, settings=settings, secrets_store=secrets_store)

    def test_l2_match_from_redact_file_returns_redact(self, tmp_path):
        from src.filter.pipeline import Decision

        (tmp_path / "scorer.py").touch()
        pipeline = self._make_pipeline(
            secrets_content="scorer.py [strategy=redact]\n",
            tmp_path=tmp_path,
            l2_matched_with_source=[("_weighted_sum", "scorer.py")],
        )
        result = pipeline.run("def _weighted_sum(): ...")
        assert result.decision == Decision.REDACT

    def test_l2_match_from_any_file_returns_redact(self, tmp_path):
        from src.filter.pipeline import Decision

        (tmp_path / "scorer.py").touch()
        pipeline = self._make_pipeline(
            secrets_content="scorer.py\n",
            tmp_path=tmp_path,
            l2_matched_with_source=[("_weighted_sum", "scorer.py")],
        )
        result = pipeline.run("def _weighted_sum(): ...")
        assert result.decision == Decision.REDACT

    def test_l1_grace_zone_l3_safe_returns_redact(self, tmp_path):
        from src.filter.pipeline import Decision

        (tmp_path / "scorer.py").touch()
        pipeline = self._make_pipeline(
            secrets_content="scorer.py\n",
            tmp_path=tmp_path,
            l2_matched_with_source=[],
            l1_score=0.82,
            l1_source_file="scorer.py",
            l3_is_leak=False,
        )
        result = pipeline.run("semantically similar prompt")
        assert result.decision == Decision.REDACT

    def test_l1_grace_zone_block_source_runs_l3(self, tmp_path):
        from src.filter.pipeline import Decision

        (tmp_path / "scorer.py").touch()
        pipeline = self._make_pipeline(
            secrets_content="scorer.py\n",
            tmp_path=tmp_path,
            l2_matched_with_source=[],
            l1_score=0.82,
            l1_source_file="scorer.py",
        )
        # L3 is mocked to return is_leak=True → BLOCK
        result = pipeline.run("semantically similar prompt")
        assert result.decision == Decision.BLOCK

    def test_hard_block_always_redacts(self, tmp_path):
        from src.filter.pipeline import Decision

        (tmp_path / "scorer.py").touch()
        pipeline = self._make_pipeline(
            secrets_content="scorer.py\n",
            tmp_path=tmp_path,
            l2_matched_with_source=[],
            l1_score=0.95,  # above hard_block_threshold
            l1_source_file="scorer.py",
        )
        result = pipeline.run("verbatim protected code")
        assert result.decision == Decision.REDACT

    def test_l2_match_from_multiple_sources_returns_redact(self, tmp_path):
        from src.filter.pipeline import Decision

        (tmp_path / "a.py").touch()
        (tmp_path / "b.py").touch()
        pipeline = self._make_pipeline(
            secrets_content="a.py [strategy=redact]\nb.py\n",
            tmp_path=tmp_path,
            l2_matched_with_source=[("_foo", "a.py"), ("_bar", "b.py")],
        )
        result = pipeline.run("uses _foo and _bar")
        assert result.decision == Decision.REDACT

    def test_inline_block_strategy_redact(self, tmp_path):
        from src.filter.pipeline import Decision

        pipeline = self._make_pipeline(
            secrets_content="@inline my_algo [strategy=redact]\ndef my_algo(): pass\n@end\n",
            tmp_path=tmp_path,
            l2_matched_with_source=[("my_algo", "@inline:my_algo")],
        )
        result = pipeline.run("call my_algo here")
        assert result.decision == Decision.REDACT

    def test_pipeline_no_longer_accepts_global_strategy(self, tmp_path):
        """FilterPipeline non accetta più il parametro strategy fisso."""
        from src.config.settings import Settings
        from src.filter.pipeline import FilterPipeline
        from src.store.secrets_store import ProtectionStrategy, SecretsStore

        secrets_file = tmp_path / "secrets"
        secrets_file.write_text("", encoding="utf-8")
        secrets_store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

        l1, l2, l3 = MagicMock(), MagicMock(), MagicMock()
        with pytest.raises(TypeError):
            FilterPipeline(
                l1=l1, l2=l2, l3=l3,
                settings=Settings(),
                secrets_store=secrets_store,
                strategy=ProtectionStrategy.BLOCK,  # parametro rimosso
            )
