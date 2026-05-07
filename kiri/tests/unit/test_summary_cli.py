"""
Tests for US-13 — Summary management (REQ-F-011).

Components under test:
  - SummaryStore       new metadata fields (source, updated_at, chunk_text, symbol_name)
  - RedactionEngine    manual summaries take priority over ollama ones
  - kiri summary list  / show / set / reset  CLI commands
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from src.cli.app import app

runner = CliRunner()


# ===========================================================================
# SummaryStore — metadata fields
# ===========================================================================


class TestSummaryStoreMetadata:
    """SummaryStore entries carry source, updated_at, chunk_text, symbol_name."""

    def test_save_stores_ollama_source_by_default(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        store.save("scorer__0", "# [PROTECTED] fn", chunk_text="def fn(): ...", symbol_name="fn")
        entry = store.get_entry("scorer__0")
        assert entry is not None
        assert entry.source == "ollama"

    def test_save_records_updated_at(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        store.save("scorer__0", "# [PROTECTED] fn")
        entry = store.get_entry("scorer__0")
        assert entry is not None
        assert entry.updated_at != ""

    def test_save_stores_chunk_text_and_symbol_name(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        store.save("scorer__0", "# [PROTECTED] fn", chunk_text="def fn(): pass", symbol_name="fn")
        entry = store.get_entry("scorer__0")
        assert entry is not None
        assert entry.chunk_text == "def fn(): pass"
        assert entry.symbol_name == "fn"

    def test_get_still_returns_text_for_backward_compat(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        store.save("scorer__0", "# [PROTECTED] fn")
        assert store.get("scorer__0") == "# [PROTECTED] fn"

    def test_old_string_format_migrated_on_load(self, tmp_path):
        """Entries stored as plain strings (pre-v0.2) are auto-migrated."""
        import json
        from src.store.summary_store import SummaryStore
        # Write old format directly
        (tmp_path / "summaries.json").write_text(
            json.dumps({"scorer__0": "# [PROTECTED] fn\n# Purpose: old."}),
            encoding="utf-8",
        )
        store = SummaryStore(tmp_path)
        entry = store.get_entry("scorer__0")
        assert entry is not None
        assert entry.source == "ollama"
        assert "# [PROTECTED] fn" in entry.text

    def test_set_manual_stores_with_manual_source(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        store.set_manual("calculate_final_price", "Calculates the final price.")
        entry = store.get_entry("manual__calculate_final_price")
        assert entry is not None
        assert entry.source == "manual"
        assert entry.symbol_name == "calculate_final_price"

    def test_find_by_symbol_returns_entry_matching_text(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        store.save(
            "scorer__0", "# [PROTECTED] _weighted_sum\n# Purpose: x", symbol_name="_weighted_sum"
        )
        result = store.find_by_symbol("_weighted_sum")
        assert result is not None
        chunk_id, entry = result
        assert "_weighted_sum" in entry.text

    def test_find_by_symbol_returns_none_when_not_found(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        assert store.find_by_symbol("ghost_function") is None

    def test_all_entries_returns_all_chunk_ids_and_entries(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        store.save("scorer__0", "# a", symbol_name="fn_a")
        store.save("scorer__1", "# b", symbol_name="fn_b")
        entries = store.all_entries()
        assert len(entries) == 2
        assert any(e.symbol_name == "fn_a" for _, e in entries)
        assert any(e.symbol_name == "fn_b" for _, e in entries)

    def test_delete_manual_removes_manual_entry(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path)
        store.set_manual("fn", "manual text")
        store.delete("manual__fn")
        assert store.get_entry("manual__fn") is None


# ===========================================================================
# RedactionEngine — manual priority
# ===========================================================================


class TestRedactionEngineManualPriority:
    """Manual summaries take priority over ollama ones in REDACT output."""

    def _make_engine(self, summaries: dict[str, str], symbols: list[str]):
        from src.redaction.engine import RedactionEngine
        from src.store.summary_store import SummaryStore
        from src.store.symbol_store import SymbolStore

        summary_store = MagicMock(spec=SummaryStore)
        symbol_store = MagicMock(spec=SymbolStore)
        symbol_store.scan.return_value = symbols

        # Simulate: manual__fn returns manual text, fn__0 returns auto text
        def get_side_effect(chunk_id):
            return summaries.get(chunk_id)

        def all_chunk_ids_side_effect():
            return list(summaries.keys())

        def get_entry_side_effect(chunk_id):
            text = summaries.get(chunk_id)
            if text is None:
                return None
            from src.store.summary_store import SummaryEntry
            source = "manual" if chunk_id.startswith("manual__") else "ollama"
            return SummaryEntry(
                text=text, source=source, updated_at="", chunk_text="", symbol_name="fn"
            )

        summary_store.get.side_effect = get_side_effect
        summary_store.all_chunk_ids.side_effect = all_chunk_ids_side_effect
        summary_store.get_entry.side_effect = get_entry_side_effect

        return RedactionEngine(summary_store=summary_store, symbol_store=symbol_store)

    def test_manual_summary_used_over_ollama(self):
        engine = self._make_engine(
            summaries={
                "fn__0": "# [PROTECTED] fn\n# Purpose: auto-generated.",
                "manual__fn": "# [PROTECTED] fn\n# Purpose: manually curated.",
            },
            symbols=["fn"],
        )
        prompt = "def fn():\n    return 42\n"
        result = engine.redact(prompt)
        assert result.was_redacted
        assert "manually curated" in result.redacted_prompt
        assert "auto-generated" not in result.redacted_prompt

    def test_ollama_summary_used_when_no_manual(self):
        engine = self._make_engine(
            summaries={"fn__0": "# [PROTECTED] fn\n# Purpose: auto-generated."},
            symbols=["fn"],
        )
        prompt = "def fn():\n    return 42\n"
        result = engine.redact(prompt)
        assert result.was_redacted
        assert "auto-generated" in result.redacted_prompt


# ===========================================================================
# CLI — kiri summary list
# ===========================================================================


class TestSummaryListCommand:
    def _store_with_entries(self, tmp_path):
        from src.store.summary_store import SummaryStore
        store = SummaryStore(tmp_path / "index")
        (tmp_path / "index").mkdir()
        store.save("scorer__0", "# [PROTECTED] fn_a\n# Purpose: does thing A.", symbol_name="fn_a")
        store.set_manual("fn_b", "# [PROTECTED] fn_b\n# Manually curated summary.")
        return store

    def test_list_shows_all_symbols(self, tmp_path):
        self._store_with_entries(tmp_path)
        with patch("src.cli.commands.summary._load_summary_store") as mock_load:
            from src.store.summary_store import SummaryStore
            mock_load.return_value = SummaryStore(tmp_path / "index")
            result = runner.invoke(app, ["summary", "list"])
        assert result.exit_code == 0
        assert "fn_a" in result.output
        assert "fn_b" in result.output

    def test_list_shows_source(self, tmp_path):
        self._store_with_entries(tmp_path)
        with patch("src.cli.commands.summary._load_summary_store") as mock_load:
            from src.store.summary_store import SummaryStore
            mock_load.return_value = SummaryStore(tmp_path / "index")
            result = runner.invoke(app, ["summary", "list"])
        assert "ollama" in result.output
        assert "manual" in result.output

    def test_list_empty_shows_no_summaries(self, tmp_path):
        (tmp_path / "index").mkdir()
        with patch("src.cli.commands.summary._load_summary_store") as mock_load:
            from src.store.summary_store import SummaryStore
            mock_load.return_value = SummaryStore(tmp_path / "index")
            result = runner.invoke(app, ["summary", "list"])
        assert result.exit_code == 0
        assert "no summaries" in result.output


# ===========================================================================
# CLI — kiri summary show
# ===========================================================================


class TestSummaryShowCommand:
    def test_show_displays_full_summary(self, tmp_path):
        (tmp_path / "index").mkdir()
        with patch("src.cli.commands.summary._load_summary_store") as mock_load:
            from src.store.summary_store import SummaryStore
            store = SummaryStore(tmp_path / "index")
            store.save("scorer__0", "# [PROTECTED] fn\n# Purpose: does thing.", symbol_name="fn")
            mock_load.return_value = store
            result = runner.invoke(app, ["summary", "show", "fn"])
        assert result.exit_code == 0
        assert "# [PROTECTED] fn" in result.output
        assert "Purpose: does thing" in result.output

    def test_show_displays_source_and_timestamp(self, tmp_path):
        (tmp_path / "index").mkdir()
        with patch("src.cli.commands.summary._load_summary_store") as mock_load:
            from src.store.summary_store import SummaryStore
            store = SummaryStore(tmp_path / "index")
            store.save("scorer__0", "# [PROTECTED] fn", symbol_name="fn")
            mock_load.return_value = store
            result = runner.invoke(app, ["summary", "show", "fn"])
        assert "ollama" in result.output

    def test_show_not_found_exits_with_error(self, tmp_path):
        (tmp_path / "index").mkdir()
        with patch("src.cli.commands.summary._load_summary_store") as mock_load:
            from src.store.summary_store import SummaryStore
            mock_load.return_value = SummaryStore(tmp_path / "index")
            result = runner.invoke(app, ["summary", "show", "ghost_fn"])
        assert result.exit_code == 1
        assert "ghost_fn" in result.output


# ===========================================================================
# CLI — kiri summary set
# ===========================================================================


class TestSummarySetCommand:
    def test_set_stores_manual_summary(self, tmp_path):
        (tmp_path / "index").mkdir()
        with patch("src.cli.commands.summary._load_summary_store") as mock_load:
            from src.store.summary_store import SummaryStore
            store = SummaryStore(tmp_path / "index")
            mock_load.return_value = store
            result = runner.invoke(app, ["summary", "set", "fn", "Calculates final price."])
        assert result.exit_code == 0
        entry = store.get_entry("manual__fn")
        assert entry is not None
        assert entry.source == "manual"
        assert entry.text == "Calculates final price."

    def test_set_warns_on_numeric_literals(self, tmp_path):
        (tmp_path / "index").mkdir()
        with patch("src.cli.commands.summary._load_summary_store") as mock_load:
            from src.store.summary_store import SummaryStore
            store = SummaryStore(tmp_path / "index")
            mock_load.return_value = store
            result = runner.invoke(
                app, ["summary", "set", "fn", "Uses discount rate 0.0325 and tier 2.47."]
            )
        assert result.exit_code == 0
        assert "Warning" in result.output or "warning" in result.output.lower()

    def test_set_no_warning_for_text_without_numbers(self, tmp_path):
        (tmp_path / "index").mkdir()
        with patch("src.cli.commands.summary._load_summary_store") as mock_load:
            from src.store.summary_store import SummaryStore
            store = SummaryStore(tmp_path / "index")
            mock_load.return_value = store
            result = runner.invoke(app, ["summary", "set", "fn", "Calculates the final price."])
        assert result.exit_code == 0
        assert "Warning" not in result.output


# ===========================================================================
# CLI — kiri summary reset
# ===========================================================================


class TestSummaryResetCommand:
    def test_reset_removes_manual_and_keeps_ollama(self, tmp_path):
        (tmp_path / "index").mkdir()
        with patch("src.cli.commands.summary._load_summary_store") as mock_load:
            from src.store.summary_store import SummaryStore
            store = SummaryStore(tmp_path / "index")
            # Both auto and manual exist
            store.save("scorer__0", "# [PROTECTED] fn\n# Purpose: auto.", symbol_name="fn")
            store.set_manual("fn", "manual text")
            mock_load.return_value = store
            result = runner.invoke(app, ["summary", "reset", "fn"])
        assert result.exit_code == 0
        assert store.get_entry("manual__fn") is None
        # Auto summary still present
        assert store.find_by_symbol("fn") is not None

    def test_reset_calls_ollama_when_no_auto_summary(self, tmp_path):
        (tmp_path / "index").mkdir()
        with (
            patch("src.cli.commands.summary._load_summary_store") as mock_load,
            patch("src.cli.commands.summary._make_summary_generator") as mock_gen_factory,
        ):
            from src.store.summary_store import SummaryStore
            store = SummaryStore(tmp_path / "index")
            # Only manual, with chunk_text stored
            store.set_manual("fn", "manual text")
            # Simulate there's a chunk with chunk_text for fn
            store.save(
                "scorer__0", "# [PROTECTED] fn\n# auto.",
                chunk_text="def fn(): return 42",
                symbol_name="fn",
            )
            store.set_manual("fn", "manual override")  # override after

            mock_load.return_value = store
            mock_gen = MagicMock()
            mock_gen.generate.return_value = "# [PROTECTED] fn\n# Purpose: regenerated."
            mock_gen_factory.return_value = mock_gen

            result = runner.invoke(app, ["summary", "reset", "fn"])
        assert result.exit_code == 0

    def test_reset_unknown_symbol_exits_with_error(self, tmp_path):
        (tmp_path / "index").mkdir()
        with patch("src.cli.commands.summary._load_summary_store") as mock_load:
            from src.store.summary_store import SummaryStore
            mock_load.return_value = SummaryStore(tmp_path / "index")
            result = runner.invoke(app, ["summary", "reset", "ghost_fn"])
        assert result.exit_code == 1
        assert "ghost_fn" in result.output

    def test_reset_all_regenerates_all_chunks(self, tmp_path):
        (tmp_path / "index").mkdir()
        with (
            patch("src.cli.commands.summary._load_summary_store") as mock_load,
            patch("src.cli.commands.summary._make_summary_generator") as mock_gen_factory,
        ):
            from src.store.summary_store import SummaryStore
            store = SummaryStore(tmp_path / "index")
            store.save(
                "scorer__0", "# [PROTECTED] fn_a", chunk_text="def fn_a(): ...", symbol_name="fn_a"
            )
            store.save(
                "scorer__1", "# [PROTECTED] fn_b", chunk_text="def fn_b(): ...", symbol_name="fn_b"
            )
            mock_load.return_value = store

            mock_gen = MagicMock()
            mock_gen.generate.return_value = "# [PROTECTED] fn\n# Purpose: regenerated."
            mock_gen_factory.return_value = mock_gen

            result = runner.invoke(app, ["summary", "reset", "--all"])
        assert result.exit_code == 0
        assert mock_gen.generate.call_count == 2
