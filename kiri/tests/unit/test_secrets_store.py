from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

# --- helpers ------------------------------------------------------------------


def make_store(tmp_path: Path):
    from src.store.secrets_store import SecretsStore

    workspace = tmp_path / "project"
    workspace.mkdir()
    gateway_dir = workspace / ".kiri"
    gateway_dir.mkdir()
    secrets_file = gateway_dir / "secrets"
    secrets_file.write_text("", encoding="utf-8")
    return SecretsStore(secrets_path=secrets_file, workspace=workspace)


# --- load ---------------------------------------------------------------------


def test_secrets_store_empty_file_returns_empty_lists(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    assert store.list_paths() == []
    assert store.list_symbols() == []


def test_secrets_store_parses_path_entries(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    (tmp_path / "project" / ".kiri" / "secrets").write_text(
        "src/engine/risk_scorer.py\nsrc/billing/\n", encoding="utf-8"
    )

    paths = store.list_paths()

    assert len(paths) == 2
    assert Path("src/engine/risk_scorer.py") in [p.relative_to(tmp_path / "project") for p in paths]


def test_secrets_store_parses_symbol_entries(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    (tmp_path / "project" / ".kiri" / "secrets").write_text(
        "@symbol RiskScorer\n@symbol sliding_window_dedup\n", encoding="utf-8"
    )

    symbols = store.list_symbols()

    assert "RiskScorer" in symbols
    assert "sliding_window_dedup" in symbols


def test_secrets_store_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    (tmp_path / "project" / ".kiri" / "secrets").write_text(
        "# this is a comment\n\nsrc/engine/risk_scorer.py\n\n", encoding="utf-8"
    )

    assert len(store.list_paths()) == 1
    assert store.list_symbols() == []


# --- add_path -----------------------------------------------------------------


def test_secrets_store_add_path_appends_entry(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    target = tmp_path / "project" / "src" / "engine" / "risk_scorer.py"
    target.parent.mkdir(parents=True)
    target.touch()

    store.add_path(target)

    assert target in store.list_paths()


def test_secrets_store_add_path_is_idempotent(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    target = tmp_path / "project" / "src" / "engine" / "risk_scorer.py"
    target.parent.mkdir(parents=True)
    target.touch()

    store.add_path(target)
    store.add_path(target)

    assert store.list_paths().count(target) == 1


# --- add_symbol ---------------------------------------------------------------


def test_secrets_store_add_symbol_appends_entry(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.add_symbol("RiskScorer")

    assert "RiskScorer" in store.list_symbols()


def test_secrets_store_add_symbol_is_idempotent(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.add_symbol("RiskScorer")
    store.add_symbol("RiskScorer")

    assert store.list_symbols().count("RiskScorer") == 1


# --- remove -------------------------------------------------------------------


def test_secrets_store_remove_path_deletes_entry(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    target = tmp_path / "project" / "src" / "engine" / "risk_scorer.py"
    target.parent.mkdir(parents=True)
    target.touch()
    store.add_path(target)

    store.remove_path(target)

    assert target not in store.list_paths()


def test_secrets_store_remove_path_nonexistent_does_not_raise(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    ghost = tmp_path / "project" / "src" / "ghost.py"

    store.remove_path(ghost)  # must not raise


def test_secrets_store_remove_symbol_deletes_entry(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.add_symbol("RiskScorer")

    store.remove_symbol("RiskScorer")

    assert "RiskScorer" not in store.list_symbols()


def test_secrets_store_remove_symbol_nonexistent_does_not_raise(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.remove_symbol("Ghost")  # must not raise


# --- atomic write -------------------------------------------------------------


def test_secrets_store_write_is_atomic(tmp_path: Path) -> None:
    # After add, no temp file should remain on disk
    store = make_store(tmp_path)
    target = tmp_path / "project" / "src" / "engine.py"
    target.parent.mkdir(parents=True)
    target.touch()

    store.add_path(target)

    temp_files = list((tmp_path / "project" / ".kiri").glob("*.tmp"))
    assert temp_files == []


# --- preserves comments -------------------------------------------------------


def test_secrets_store_preserves_comments_on_write(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    secrets_file = tmp_path / "project" / ".kiri" / "secrets"
    secrets_file.write_text("# protected files\n\n", encoding="utf-8")

    store.add_symbol("RiskScorer")

    content = secrets_file.read_text(encoding="utf-8")
    assert "# protected files" in content



# --- temp file permissions ----------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX chmod only")
def test_atomic_write_produces_owner_only_file(tmp_path: Path) -> None:
    """secrets file written via _atomic_write must not be group/other-readable."""
    store = make_store(tmp_path)
    store.add_path(tmp_path / "project" / "src" / "scorer.py")

    mode = stat.S_IMODE(store.secrets_path.stat().st_mode)
    assert mode & 0o077 == 0, f"secrets file is too permissive: {oct(mode)}"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX chmod only")
def test_symbol_store_atomic_write_owner_only(tmp_path: Path) -> None:
    """symbols.json written via _save must not be group/other-readable."""
    from src.store.symbol_store import SymbolStore

    store = SymbolStore(index_dir=tmp_path)
    store.add("src/scorer.py", ["RiskScorer", "compute"])

    symbols_file = tmp_path / "symbols.json"
    mode = stat.S_IMODE(symbols_file.stat().st_mode)
    assert mode & 0o077 == 0, f"symbols.json is too permissive: {oct(mode)}"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX chmod only")
def test_summary_store_atomic_write_owner_only(tmp_path: Path) -> None:
    """summaries.json written via _save must not be group/other-readable."""
    from src.store.summary_store import SummaryStore

    store = SummaryStore(index_dir=tmp_path)
    store.save("chunk_001", "This function computes the risk score.")

    summaries_file = tmp_path / "summaries.json"
    mode = stat.S_IMODE(summaries_file.stat().st_mode)
    assert mode & 0o077 == 0, f"summaries.json is too permissive: {oct(mode)}"
