"""
TDD tests for the redaction feature (US-R1 through US-R5 + admin auth).

Components under test:
  - SummaryStore        persist Ollama-generated summaries per chunk
  - SummaryGenerator    call Ollama to produce a safe summary of a chunk
  - RedactionEngine     find protected spans in a prompt and replace with summaries
  - ProtectionStrategy  per-file strategy (block | redact) stored in SecretsStore
  - AdminAuth           only admin key may change strategy or remove protection
  - Pipeline            REDACT decision returned instead of BLOCK when strategy=redact
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ===========================================================================
# SummaryStore — US-R1
# ===========================================================================


class TestSummaryStore:
    """Persist and retrieve chunk summaries to/from disk."""

    def test_save_and_get_summary(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        store.save("scorer__3", "# [PROTECTED] _weighted_sum\n# Scopo: media pesata scores.")
        result = store.get("scorer__3")
        assert result is not None
        assert "_weighted_sum" in result

    def test_get_missing_returns_none(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        assert store.get("nonexistent__0") is None

    def test_has_returns_true_after_save(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        store.save("scorer__3", "some summary")
        assert store.has("scorer__3")

    def test_has_returns_false_when_missing(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        assert not store.has("scorer__3")

    def test_summaries_persist_across_instances(self, tmp_path):
        from src.store.summary_store import SummaryStore
        SummaryStore(tmp_path).save("scorer__3", "summary text")
        result = SummaryStore(tmp_path).get("scorer__3")
        assert result == "summary text"

    def test_save_overwrites_existing(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        store.save("scorer__3", "old summary")
        store.save("scorer__3", "new summary")
        assert store.get("scorer__3") == "new summary"

    def test_delete_removes_entry(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        store.save("scorer__3", "summary")
        store.delete("scorer__3")
        assert store.get("scorer__3") is None

    def test_delete_nonexistent_does_not_raise(self, tmp_path):
        from src.store.summary_store import SummaryStore
        SummaryStore(tmp_path).delete("ghost__0")  # must not raise

    def test_all_chunk_ids(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        store.save("scorer__0", "a")
        store.save("scorer__1", "b")
        ids = store.all_chunk_ids()
        assert "scorer__0" in ids
        assert "scorer__1" in ids


# ===========================================================================
# SummaryGenerator — US-R1
# ===========================================================================


class TestSummaryGenerator:
    """Call Ollama to generate a safe public summary of a protected chunk."""

    def test_generate_returns_string(self, tmp_path):
        from src.config.settings import Settings
        from src.redaction.summary_generator import SummaryGenerator

        mock_client = MagicMock()
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = {
            "response": "# [PROTECTED] _weighted_sum\n# Scopo: media pesata."
        }

        gen = SummaryGenerator(Settings(), http_client=mock_client)
        result = gen.generate(
            chunk_id="scorer__3",
            chunk_text="def _weighted_sum(components):\n    return sum(...)",
            symbol_name="_weighted_sum",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_calls_ollama_with_prompt(self, tmp_path):
        from src.config.settings import Settings
        from src.redaction.summary_generator import SummaryGenerator

        mock_client = MagicMock()
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = {"response": "# summary"}

        gen = SummaryGenerator(Settings(), http_client=mock_client)
        gen.generate("scorer__3", "def _weighted_sum(): ...", "_weighted_sum")

        call_kwargs = mock_client.post.call_args
        body = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs[0][1]
        assert "_weighted_sum" in str(body) or "weighted_sum" in str(body)

    def test_generate_raises_on_ollama_unavailable(self):
        import httpx

        from src.config.settings import Settings
        from src.redaction.summary_generator import SummaryGenerationError, SummaryGenerator

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("refused")

        gen = SummaryGenerator(Settings(), http_client=mock_client)
        with pytest.raises(SummaryGenerationError):
            gen.generate("scorer__3", "def _weighted_sum(): ...", "_weighted_sum")

    def test_generate_summary_does_not_contain_implementation(self):
        """The generated summary must not contain the original code body."""
        from src.config.settings import Settings
        from src.redaction.summary_generator import SummaryGenerator

        secret_body = "return sum(components[k] * weights[k] for k in weights)"  # noqa: S105
        mock_client = MagicMock()
        mock_client.post.return_value.status_code = 200
        # Ollama correctly returns only the summary, not the implementation
        mock_client.post.return_value.json.return_value = {
            "response": "# [PROTECTED] _weighted_sum\n# Scopo: calcola media pesata."
        }

        gen = SummaryGenerator(Settings(), http_client=mock_client)
        result = gen.generate("scorer__3", secret_body, "_weighted_sum")
        assert secret_body not in result


# ===========================================================================
# RedactionEngine — US-R2, US-R3
# ===========================================================================


class TestRedactionEngine:
    """Find protected spans in a prompt and replace with pre-generated summaries."""

    def _make_engine(self, summaries: dict[str, str], symbols: list[str] = None):
        from src.redaction.engine import RedactionEngine
        from src.store.summary_store import SummaryStore
        from src.store.symbol_store import SymbolStore

        summary_store = MagicMock(spec=SummaryStore)
        summary_store.get.side_effect = lambda chunk_id: summaries.get(chunk_id)

        symbol_store = MagicMock(spec=SymbolStore)
        symbol_store.scan.return_value = symbols or []

        return RedactionEngine(
            summary_store=summary_store,
            symbol_store=symbol_store,
        )

    def test_redact_preserves_signature_and_stubs_body(self):
        engine = self._make_engine(
            summaries={},
            symbols=["_weighted_sum"],
        )

        prompt = (
            "Aiutami con questo codice:\n\n"
            "def _weighted_sum(components):\n"
            "    weights = {'payment_history': 0.341}\n"
            "    return sum(components[k] * weights[k] for k in weights)\n"
        )

        result = engine.redact(prompt)

        assert result.was_redacted
        # signature is preserved — Claude can reason about the function without seeing the body
        assert "def _weighted_sum(components):" in result.redacted_prompt
        # body is gone
        assert "0.341" not in result.redacted_prompt
        assert "weights = {" not in result.redacted_prompt
        # stub marker is present
        assert "[PROTECTED: implementation is confidential]" in result.redacted_prompt

    def test_redact_returns_original_when_no_match(self):
        engine = self._make_engine(summaries={}, symbols=[])
        prompt = "Come posso migliorare le performance della mia app?"
        result = engine.redact(prompt)
        assert not result.was_redacted
        assert result.redacted_prompt == prompt

    def test_redact_records_what_was_replaced(self):
        engine = self._make_engine(
            summaries={"scorer__3": "# [PROTECTED] _weighted_sum"},
            symbols=["_weighted_sum"],
        )
        prompt = "def _weighted_sum(components):\n    return sum()\n"
        result = engine.redact(prompt)
        assert len(result.redacted_spans) >= 1
        assert any("_weighted_sum" in span.symbol for span in result.redacted_spans)

    def test_redact_stubs_body_regardless_of_summary(self):
        """Body is always replaced with a signature-preserving stub, with or without a summary."""
        engine = self._make_engine(
            summaries={},
            symbols=["_weighted_sum"],
        )
        prompt = "def _weighted_sum(components):\n    return sum()\n"
        result = engine.redact(prompt)
        assert result.was_redacted
        assert "def _weighted_sum(components):" in result.redacted_prompt
        assert "return sum()" not in result.redacted_prompt
        assert "[PROTECTED: implementation is confidential]" in result.redacted_prompt

    def test_redact_multiple_symbols_in_same_prompt(self):
        engine = self._make_engine(
            summaries={
                "scorer__3": "# [PROTECTED] _weighted_sum",
                "scorer__4": "# [PROTECTED] _score_utilization",
            },
            symbols=["_weighted_sum", "_score_utilization"],
        )
        prompt = (
            "def _weighted_sum(c): return 0\n"
            "def _score_utilization(r): return 1\n"
        )
        result = engine.redact(prompt)
        assert result.was_redacted
        assert len(result.redacted_spans) == 2

    def test_redact_does_not_modify_non_protected_functions(self):
        engine = self._make_engine(
            summaries={"scorer__3": "# [PROTECTED] _weighted_sum"},
            symbols=["_weighted_sum"],
        )
        prompt = (
            "def _weighted_sum(c): return 0\n\n"
            "def public_helper(x): return x + 1\n"
        )
        result = engine.redact(prompt)
        assert "public_helper" in result.redacted_prompt
        assert "x + 1" in result.redacted_prompt


# ===========================================================================
# ProtectionStrategy — US-R5
# ===========================================================================


class TestProtectionStrategy:
    """Per-file strategy: block (default) or redact."""

    def test_default_strategy_is_block(self, tmp_path):
        from src.store.secrets_store import ProtectionStrategy

        store = _make_store(tmp_path, "src/scorer.py\n")
        strategy = store.get_strategy(tmp_path / "project" / "src" / "scorer.py")
        assert strategy == ProtectionStrategy.BLOCK

    def test_explicit_redact_strategy_parsed(self, tmp_path):
        from src.store.secrets_store import ProtectionStrategy

        store = _make_store(tmp_path, "src/scorer.py [strategy=redact]\n")
        (tmp_path / "project" / "src").mkdir(parents=True)
        (tmp_path / "project" / "src" / "scorer.py").touch()
        strategy = store.get_strategy(tmp_path / "project" / "src" / "scorer.py")
        assert strategy == ProtectionStrategy.REDACT

    def test_explicit_block_strategy_parsed(self, tmp_path):
        from src.store.secrets_store import ProtectionStrategy

        store = _make_store(tmp_path, "src/scorer.py [strategy=block]\n")
        (tmp_path / "project" / "src").mkdir(parents=True)
        (tmp_path / "project" / "src" / "scorer.py").touch()
        strategy = store.get_strategy(tmp_path / "project" / "src" / "scorer.py")
        assert strategy == ProtectionStrategy.BLOCK

    def test_unknown_file_returns_block(self, tmp_path):
        from src.store.secrets_store import ProtectionStrategy

        store = _make_store(tmp_path, "")
        strategy = store.get_strategy(tmp_path / "project" / "ghost.py")
        assert strategy == ProtectionStrategy.BLOCK


# ===========================================================================
# AdminAuth — only admin may change strategy or remove protection
# ===========================================================================

# ===========================================================================
# Pipeline integration — REDACT decision
# ===========================================================================


class TestPipelineRedactDecision:
    """Pipeline returns REDACT instead of BLOCK when strategy=redact."""

    def _make_pipeline(self, strategy, l2_matched=None, l1_score=0.5, tmp_path=None):
        import tempfile
        from pathlib import Path

        from src.config.settings import Settings
        from src.filter.l3_classifier import L3Result
        from src.filter.pipeline import FilterPipeline
        from src.store.secrets_store import SecretsStore

        # Build a secrets store with a single sentinel file annotated with
        # the requested strategy, so the pipeline resolves it correctly.
        strategy_str = strategy.value  # "block" or "redact"
        tmp = Path(tempfile.mkdtemp()) if tmp_path is None else tmp_path
        secrets_file = tmp / "secrets"
        sentinel = "src/scorer.py"
        (tmp / "src").mkdir(exist_ok=True)
        (tmp / "src" / "scorer.py").touch()
        secrets_file.write_text(f"{sentinel} [strategy={strategy_str}]\n", encoding="utf-8")
        secrets_store = SecretsStore(secrets_path=secrets_file, workspace=tmp)

        l1 = MagicMock()
        l1.check.return_value = MagicMock(top_score=l1_score, top_source_file=sentinel)

        l2 = MagicMock()
        l2_syms = l2_matched or []
        l2_result = MagicMock()
        l2_result.matched = l2_syms
        # Route all L2 matches through the sentinel source
        l2_result.matched_with_source = [(s, sentinel) for s in l2_syms]
        l2.check.return_value = l2_result

        l3 = MagicMock()
        l3.check.return_value = L3Result(is_leak=False)

        settings = Settings()
        return FilterPipeline(l1=l1, l2=l2, l3=l3, settings=settings, secrets_store=secrets_store)

    def test_block_strategy_returns_redact_on_l2_match(self):
        from src.filter.pipeline import Decision
        from src.store.secrets_store import ProtectionStrategy

        pipeline = self._make_pipeline(
            strategy=ProtectionStrategy.BLOCK,
            l2_matched=["_weighted_sum"],
        )
        result = pipeline.run("def _weighted_sum(): ...")
        assert result.decision == Decision.REDACT

    def test_redact_strategy_returns_redact_on_l2_match(self):
        from src.filter.pipeline import Decision
        from src.store.secrets_store import ProtectionStrategy

        pipeline = self._make_pipeline(
            strategy=ProtectionStrategy.REDACT,
            l2_matched=["_weighted_sum"],
        )
        result = pipeline.run("def _weighted_sum(): ...")
        assert result.decision == Decision.REDACT

    def test_redact_strategy_returns_redact_on_l1_grace_zone(self):
        from src.filter.pipeline import Decision
        from src.store.secrets_store import ProtectionStrategy

        pipeline = self._make_pipeline(
            strategy=ProtectionStrategy.REDACT,
            l2_matched=[],
            l1_score=0.82,  # in grace zone
        )
        result = pipeline.run("some semantically similar prompt")
        assert result.decision == Decision.REDACT

    def test_redact_strategy_passes_below_threshold(self):
        from src.filter.pipeline import Decision
        from src.store.secrets_store import ProtectionStrategy

        pipeline = self._make_pipeline(
            strategy=ProtectionStrategy.REDACT,
            l2_matched=[],
            l1_score=0.50,
        )
        result = pipeline.run("completely unrelated prompt")
        assert result.decision == Decision.PASS

    def test_hard_block_always_redacts(self):
        """score >= hard_block_threshold always returns REDACT."""
        from src.filter.pipeline import Decision
        from src.store.secrets_store import ProtectionStrategy

        pipeline = self._make_pipeline(
            strategy=ProtectionStrategy.REDACT,
            l2_matched=[],
            l1_score=0.95,  # above hard_block_threshold
        )
        result = pipeline.run("verbatim protected code")
        assert result.decision == Decision.REDACT


# ===========================================================================
# Watcher integration — summary generation on index
# ===========================================================================


class TestWatcherSummaryGeneration:
    """When indexing, Watcher generates and stores summaries for each chunk."""

    def test_index_path_generates_summary_for_all_chunks(self, tmp_path):
        """Summaries are generated for all functions — public and private alike.

        A developer debugging code that calls private helpers benefits from knowing
        their purpose, so we generate summaries regardless of visibility.
        """
        from src.config.settings import Settings
        from src.indexer.chunker import chunk
        from src.indexer.embedder import Embedder
        from src.indexer.watcher import Watcher
        from src.redaction.summary_generator import SummaryGenerator
        from src.store.secrets_store import SecretsStore
        from src.store.summary_store import SummaryStore
        from src.store.symbol_store import SymbolStore
        from src.store.vector_store import VectorStore

        settings = Settings()
        index_dir = tmp_path / "index"
        index_dir.mkdir()

        scorer = tmp_path / "scorer.py"
        scorer.write_text(
            "def compute_score(components):\n    return sum(components.values())\n\n"
            "def _scale(raw):\n    return round(300 + raw * 550)\n",
            encoding="utf-8",
        )

        secrets_file = tmp_path / "secrets"
        secrets_file.write_text("", encoding="utf-8")
        secrets_store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

        vs = VectorStore(index_dir)
        ss = SymbolStore(index_dir)
        summary_store = SummaryStore(index_dir)

        gen_mock = MagicMock(spec=SummaryGenerator)
        gen_mock.generate.return_value = "# [PROTECTED] func\n# Purpose: calcola score."

        extractor_mock = MagicMock()
        extractor_mock.extract.return_value = []
        extractor_mock.filter_symbols.side_effect = lambda syms, path: syms

        watcher = Watcher(
            secrets_store=secrets_store,
            vector_store=vs,
            symbol_store=ss,
            chunker=chunk,
            embedder=Embedder(settings),
            extractor=extractor_mock,
            summary_generator=gen_mock,
            summary_store=summary_store,
        )
        watcher.index_path(scorer)

        # Both chunks (public + private) should trigger a generate call
        assert gen_mock.generate.call_count == vs.count()

    def test_index_path_skips_summary_when_generator_unavailable(self, tmp_path):
        """If Ollama is down, indexing completes without summaries — no exception."""
        from src.config.settings import Settings
        from src.indexer.chunker import chunk
        from src.indexer.embedder import Embedder
        from src.indexer.watcher import Watcher
        from src.redaction.summary_generator import SummaryGenerationError, SummaryGenerator
        from src.store.secrets_store import SecretsStore
        from src.store.summary_store import SummaryStore
        from src.store.symbol_store import SymbolStore
        from src.store.vector_store import VectorStore

        settings = Settings()
        index_dir = tmp_path / "index"
        index_dir.mkdir()

        scorer = tmp_path / "scorer.py"
        scorer.write_text(
            "def _weighted_sum(components):\n    return sum(components.values())\n",
            encoding="utf-8",
        )

        secrets_file = tmp_path / "secrets"
        secrets_file.write_text("", encoding="utf-8")
        secrets_store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

        gen_mock = MagicMock(spec=SummaryGenerator)
        gen_mock.generate.side_effect = SummaryGenerationError("Ollama down")

        extractor_mock = MagicMock()
        extractor_mock.extract.return_value = []
        extractor_mock.filter_symbols.side_effect = lambda syms, path: syms

        summary_store = SummaryStore(index_dir)

        watcher = Watcher(
            secrets_store=secrets_store,
            vector_store=VectorStore(index_dir),
            symbol_store=SymbolStore(index_dir),
            chunker=chunk,
            embedder=Embedder(settings),
            extractor=extractor_mock,
            summary_generator=gen_mock,
            summary_store=summary_store,
        )
        watcher.index_path(scorer)  # must not raise

        # Chunks indexed but no summaries
        assert summary_store.all_chunk_ids() == []


class TestWatcherChunkNamesAlwaysIndexed:
    """Chunk names (tree-sitter method/class names) must be in the symbol store
    even when Ollama's filter_symbols would have discarded them as 'generic'."""

    def test_chunk_names_in_symbol_store_even_if_ollama_filters_them(self, tmp_path):
        """computePrice should be in symbol store even if Ollama returns []."""
        from src.config.settings import Settings
        from src.indexer.chunker import chunk
        from src.indexer.embedder import Embedder
        from src.indexer.watcher import Watcher
        from src.store.secrets_store import SecretsStore
        from src.store.symbol_store import SymbolStore
        from src.store.vector_store import VectorStore

        settings = Settings()
        index_dir = tmp_path / "index"
        index_dir.mkdir()

        src_file = tmp_path / "engine.py"
        src_file.write_text(
            "def computePrice(base, demand):\n    return base * demand\n\n"
            "def applyDiscount(price, pct):\n    return price * (1 - pct)\n",
            encoding="utf-8",
        )

        secrets_file = tmp_path / "secrets"
        secrets_file.write_text("", encoding="utf-8")
        secrets_store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

        # Simulate Ollama filtering out all method names as "too generic"
        extractor_mock = MagicMock()
        extractor_mock.filter_symbols.return_value = []

        ss = SymbolStore(index_dir)
        watcher = Watcher(
            secrets_store=secrets_store,
            vector_store=VectorStore(index_dir),
            symbol_store=ss,
            chunker=chunk,
            embedder=Embedder(settings),
            extractor=extractor_mock,
        )
        watcher.index_path(src_file)

        known = ss.scan("computePrice applyDiscount")
        assert "computePrice" in known, "chunk name must be indexed regardless of Ollama filter"
        assert "applyDiscount" in known, "chunk name must be indexed regardless of Ollama filter"


    def test_def_in_prompt_triggers_brace_stub_when_chunk_name_indexed(self, tmp_path):
        """When computePrice is in symbol store, pasting its body should stub the block."""
        from src.config.settings import Settings
        from src.indexer.chunker import chunk
        from src.indexer.embedder import Embedder
        from src.indexer.watcher import Watcher
        from src.redaction.engine import RedactionEngine
        from src.store.secrets_store import SecretsStore
        from src.store.summary_store import SummaryStore
        from src.store.symbol_store import SymbolStore
        from src.store.vector_store import VectorStore

        settings = Settings()
        index_dir = tmp_path / "index"
        index_dir.mkdir()

        src_file = tmp_path / "engine.py"
        src_file.write_text(
            "def computePrice(base, demand):\n    return base * demand * 1.7\n",
            encoding="utf-8",
        )

        secrets_file = tmp_path / "secrets"
        secrets_file.write_text("", encoding="utf-8")
        secrets_store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

        extractor_mock = MagicMock()
        extractor_mock.filter_symbols.return_value = []

        ss = SymbolStore(index_dir)
        watcher = Watcher(
            secrets_store=secrets_store,
            vector_store=VectorStore(index_dir),
            symbol_store=ss,
            chunker=chunk,
            embedder=Embedder(settings),
            extractor=extractor_mock,
        )
        watcher.index_path(src_file)

        engine = RedactionEngine(
            summary_store=SummaryStore(index_dir),
            symbol_store=ss,
        )
        prompt = (
            "Can you review this?\n\n"
            "def computePrice(base, demand):\n"
            "    # proprietary: exponent 1.7 from A/B test\n"
            "    return base * demand * 1.7\n"
        )
        result = engine.redact(prompt)
        assert result.was_redacted
        # Body must be gone
        assert "1.7" not in result.redacted_prompt
        assert "A/B test" not in result.redacted_prompt
        # Signature must be preserved
        assert "def computePrice" in result.redacted_prompt


    def test_def_in_prompt_triggers_brace_stub(self, tmp_path):
        """Java brace block is stubbed when method name is in symbol store."""
        from src.redaction.engine import RedactionEngine
        from src.store.summary_store import SummaryStore
        from src.store.symbol_store import SymbolStore

        index_dir = tmp_path / "index"
        index_dir.mkdir()

        ss = SymbolStore(index_dir)
        ss.add("engine.java", ["computePrice"])

        engine = RedactionEngine(
            summary_store=SummaryStore(index_dir),
            symbol_store=ss,
        )
        prompt = (
            "Review this Java:\n\n"
            "public double computePrice(double base, double demand) {\n"
            "    // proprietary: exponent 1.7\n"
            "    return base * Math.pow(demand, 1.7);\n"
            "}\n"
        )
        result = engine.redact(prompt)
        assert result.was_redacted
        assert "1.7" not in result.redacted_prompt
        assert "proprietary" not in result.redacted_prompt
        assert "computePrice" in result.redacted_prompt


    def test_index_inline_block_generates_summary(self, tmp_path):
        """index_inline_block deve chiamare il summary generator per ogni chunk."""
        from src.config.settings import Settings
        from src.indexer.chunker import chunk
        from src.indexer.embedder import Embedder
        from src.indexer.watcher import Watcher
        from src.redaction.summary_generator import SummaryGenerator
        from src.store.secrets_store import InlineBlock, SecretsStore
        from src.store.summary_store import SummaryStore
        from src.store.symbol_store import SymbolStore
        from src.store.vector_store import VectorStore

        settings = Settings()
        index_dir = tmp_path / "index"
        index_dir.mkdir()

        secrets_file = tmp_path / "secrets"
        secrets_file.write_text("", encoding="utf-8")
        secrets_store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

        summary_store = SummaryStore(index_dir)
        gen_mock = MagicMock(spec=SummaryGenerator)
        gen_mock.generate.return_value = "# [PROTECTED]\n# Calcola il punteggio."

        extractor_mock = MagicMock()
        extractor_mock.extract.return_value = []
        extractor_mock.filter_symbols.side_effect = lambda syms, path: syms

        watcher = Watcher(
            secrets_store=secrets_store,
            vector_store=VectorStore(index_dir),
            symbol_store=SymbolStore(index_dir),
            chunker=chunk,
            embedder=Embedder(settings),
            extractor=extractor_mock,
            summary_generator=gen_mock,
            summary_store=summary_store,
        )

        block = InlineBlock(
            name="my_algo",
            content="def my_algo(x):\n    return x * 1.337\n",
        )
        watcher.index_inline_block(block)

        assert gen_mock.generate.call_count >= 1
        assert len(summary_store.all_chunk_ids()) >= 1

    def test_index_inline_block_skips_summary_on_error(self, tmp_path):
        """SummaryGenerationError durante inline block non deve propagare."""
        from src.config.settings import Settings
        from src.indexer.chunker import chunk
        from src.indexer.embedder import Embedder
        from src.indexer.watcher import Watcher
        from src.redaction.summary_generator import SummaryGenerationError, SummaryGenerator
        from src.store.secrets_store import InlineBlock, SecretsStore
        from src.store.summary_store import SummaryStore
        from src.store.symbol_store import SymbolStore
        from src.store.vector_store import VectorStore

        settings = Settings()
        index_dir = tmp_path / "index"
        index_dir.mkdir()

        secrets_file = tmp_path / "secrets"
        secrets_file.write_text("", encoding="utf-8")
        secrets_store = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

        gen_mock = MagicMock(spec=SummaryGenerator)
        gen_mock.generate.side_effect = SummaryGenerationError("Ollama down")
        summary_store = SummaryStore(index_dir)

        extractor_mock = MagicMock()
        extractor_mock.extract.return_value = []
        extractor_mock.filter_symbols.side_effect = lambda syms, path: syms

        watcher = Watcher(
            secrets_store=secrets_store,
            vector_store=VectorStore(index_dir),
            symbol_store=SymbolStore(index_dir),
            chunker=chunk,
            embedder=Embedder(settings),
            extractor=extractor_mock,
            summary_generator=gen_mock,
            summary_store=summary_store,
        )

        block = InlineBlock(name="secret_fn", content="def secret_fn():\n    return 42\n")
        watcher.index_inline_block(block)  # must not raise

        assert summary_store.all_chunk_ids() == []


# ===========================================================================
# Helpers
# ===========================================================================


def _make_store(tmp_path: Path, content: str):
    from src.store.secrets_store import SecretsStore
    workspace = tmp_path / "project"
    workspace.mkdir(exist_ok=True)
    gw = workspace / ".kiri"
    gw.mkdir(exist_ok=True)
    secrets = gw / "secrets"
    secrets.write_text(content, encoding="utf-8")
    return SecretsStore(secrets_path=secrets, workspace=workspace)
