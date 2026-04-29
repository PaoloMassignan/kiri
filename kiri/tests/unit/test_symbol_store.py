from __future__ import annotations

from pathlib import Path

# --- helpers ------------------------------------------------------------------


def make_store(tmp_path: Path):
    from src.store.symbol_store import SymbolStore

    index_dir = tmp_path / "index"
    index_dir.mkdir()
    return SymbolStore(index_dir=index_dir)


# --- add / symbols_for --------------------------------------------------------


def test_symbol_store_empty_on_creation(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    assert store.all_symbols() == set()


def test_symbol_store_add_stores_symbols_for_file(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.add("src/engine/risk_scorer.py", ["RiskScorer", "sliding_window_dedup"])

    assert store.symbols_for("src/engine/risk_scorer.py") == ["RiskScorer", "sliding_window_dedup"]


def test_symbol_store_add_overwrites_existing_entry(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("src/engine/risk_scorer.py", ["RiskScorer"])

    store.add("src/engine/risk_scorer.py", ["RiskScorer", "DataFlowEngine"])

    assert store.symbols_for("src/engine/risk_scorer.py") == ["RiskScorer", "DataFlowEngine"]


def test_symbol_store_add_multiple_files(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("src/engine/risk_scorer.py", ["RiskScorer"])
    store.add("src/billing/engine.py", ["BillingEngine", "compute_margin"])

    assert len(store.all_symbols()) == 3


# --- explicit symbols ---------------------------------------------------------


def test_symbol_store_add_explicit_stores_under_explicit_key(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.add_explicit(["RiskScorer", "DataFlowEngine"])

    assert "RiskScorer" in store.all_symbols()
    assert "DataFlowEngine" in store.all_symbols()


def test_symbol_store_explicit_symbols_merged_in_all_symbols(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("src/engine.py", ["EngineA"])
    store.add_explicit(["ExplicitSymbol"])

    symbols = store.all_symbols()

    assert "EngineA" in symbols
    assert "ExplicitSymbol" in symbols


# --- remove -------------------------------------------------------------------


def test_symbol_store_remove_deletes_file_entry(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("src/engine/risk_scorer.py", ["RiskScorer"])

    store.remove("src/engine/risk_scorer.py")

    assert store.symbols_for("src/engine/risk_scorer.py") == []
    assert "RiskScorer" not in store.all_symbols()


def test_symbol_store_remove_nonexistent_does_not_raise(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.remove("src/ghost.py")  # must not raise


def test_symbol_store_remove_does_not_affect_other_files(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("src/engine.py", ["EngineA"])
    store.add("src/billing.py", ["BillingB"])

    store.remove("src/engine.py")

    assert "BillingB" in store.all_symbols()


# --- all_symbols --------------------------------------------------------------


def test_symbol_store_all_symbols_returns_union(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("src/a.py", ["Alpha", "Beta"])
    store.add("src/b.py", ["Beta", "Gamma"])

    symbols = store.all_symbols()

    assert symbols == {"Alpha", "Beta", "Gamma"}


# --- scan ---------------------------------------------------------------------


def test_symbol_store_scan_finds_present_symbol(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("src/engine.py", ["RiskScorer"])

    matches = store.scan("please refactor RiskScorer for me")

    assert "RiskScorer" in matches


def test_symbol_store_scan_returns_empty_when_no_match(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("src/engine.py", ["RiskScorer"])

    matches = store.scan("how do I implement a binary search?")

    assert matches == []


def test_symbol_store_scan_whole_word_does_not_match_substring(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("src/engine.py", ["RiskScorer"])

    # RiskScorer is a substring of RiskScorerV2 — must NOT match
    matches = store.scan("refactor RiskScorerV2 class")

    assert "RiskScorer" not in matches


def test_symbol_store_scan_whole_word_does_not_match_prefix(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("src/engine.py", ["Risk"])

    # Risk is a prefix of RiskScorer — must NOT match
    matches = store.scan("refactor RiskScorer class")

    assert "Risk" not in matches


def test_symbol_store_scan_finds_multiple_symbols(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("src/engine.py", ["RiskScorer", "sliding_window_dedup", "DataFlowEngine"])

    matches = store.scan("can you refactor RiskScorer and sliding_window_dedup?")

    assert "RiskScorer" in matches
    assert "sliding_window_dedup" in matches
    assert "DataFlowEngine" not in matches


def test_symbol_store_scan_is_case_sensitive(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add("src/engine.py", ["RiskScorer"])

    matches = store.scan("refactor riskscorer class")

    assert matches == []


def test_symbol_store_scan_includes_explicit_symbols(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add_explicit(["DataFlowEngine"])

    matches = store.scan("how does DataFlowEngine work?")

    assert "DataFlowEngine" in matches


# --- persistence --------------------------------------------------------------


def test_symbol_store_persists_across_instances(tmp_path: Path) -> None:
    from src.store.symbol_store import SymbolStore

    index_dir = tmp_path / "index"
    index_dir.mkdir()

    store1 = SymbolStore(index_dir=index_dir)
    store1.add("src/engine.py", ["RiskScorer"])

    store2 = SymbolStore(index_dir=index_dir)

    assert "RiskScorer" in store2.all_symbols()


# --- atomic write -------------------------------------------------------------


def test_symbol_store_no_temp_files_after_write(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.add("src/engine.py", ["RiskScorer"])

    temp_files = list((tmp_path / "index").glob("*.tmp"))
    assert temp_files == []


# --- _count_sig_figs -----------------------------------------------------------


def _sf(raw: str) -> int:
    from src.store.symbol_store import _count_sig_figs
    return _count_sig_figs(raw)


class TestCountSigFigs:
    """Trailing zeros after the decimal point must not inflate the count."""

    # Decimal: trailing zeros stripped
    def test_trailing_zeros_stripped_from_decimal(self):
        assert _sf("0.4632247000000") == 7

    def test_trailing_zeros_match_clean_form(self):
        assert _sf("0.4632247000000") == _sf("0.4632247")

    def test_one_point_zero_zero_equals_one(self):
        """1.00 and 1 represent the same precision — both give 1."""
        assert _sf("1.00") == 1
        assert _sf("1.00") == _sf("1")

    def test_four_point_zero_gives_one(self):
        assert _sf("4.0") == 1

    def test_one_point_five_unchanged(self):
        """1.5 has no trailing zeros — must not be affected."""
        assert _sf("1.5") == 2

    def test_zero_point_three_two_five_unchanged(self):
        assert _sf("0.0325") == 3

    def test_decimal_with_inner_zeros_unchanged(self):
        """0.046439909 — no trailing zeros, must not be affected."""
        assert _sf("0.046439909") == 8

    def test_release_time_trailing_zero(self):
        """0.120 — trailing zero stripped → same as 0.12."""
        assert _sf("0.120") == 2
        assert _sf("0.120") == _sf("0.12")

    # Integers: trailing zeros are NOT stripped
    def test_integer_trailing_zeros_kept(self):
        """44100 is an integer — trailing zero is part of the magnitude."""
        assert _sf("44100") == 5

    def test_integer_18000(self):
        assert _sf("18000") == 5

    def test_integer_2048_unchanged(self):
        assert _sf("2048") == 4

    def test_integer_100(self):
        assert _sf("100") == 3

    # Percentages
    def test_percentage_no_trailing_zeros(self):
        assert _sf("22%") == 2

    def test_percentage_with_trailing_zeros(self):
        assert _sf("22.00%") == 2
        assert _sf("22.00%") == _sf("22%")

    # Scientific notation (mantissa only)
    def test_scientific_notation_mantissa(self):
        assert _sf("1.0e-15") == 1

    def test_scientific_notation_multi_digit(self):
        assert _sf("1.47e-3") == 3

    # scan_numbers integration: prompt with trailing zeros still blocks
    def test_scan_numbers_blocks_trailing_zero_variant(self, tmp_path: Path):
        from src.store.symbol_store import SymbolStore
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        store = SymbolStore(index_dir=index_dir)
        # protected constant: 0.4632247 (7 sig figs)
        store.add_numbers("src/engine.py", [(0.4632247, 7)])

        matched = store.scan_numbers("il valore è 0.4632247000000")

        assert len(matched) == 1

    def test_scan_numbers_does_not_block_fewer_sig_figs(self, tmp_path: Path):
        from src.store.symbol_store import SymbolStore
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        store = SymbolStore(index_dir=index_dir)
        store.add_numbers("src/engine.py", [(0.4632247, 7)])

        matched = store.scan_numbers("il valore è circa 0.463")

        assert matched == []
