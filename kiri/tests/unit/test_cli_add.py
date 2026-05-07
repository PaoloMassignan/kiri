from __future__ import annotations

from pathlib import Path

import pytest

from src.config.settings import Settings

# --- fakes --------------------------------------------------------------------


class FakeSecretsStore:
    def __init__(self) -> None:
        self.added_paths: list[Path] = []
        self.added_symbols: list[str] = []
        self.added_globs: list[str] = []

    def add_path(self, path: Path) -> None:
        self.added_paths.append(path)

    def add_symbol(self, symbol: str) -> None:
        self.added_symbols.append(symbol)

    def add_glob(self, pattern: str) -> None:
        self.added_globs.append(pattern)

    def expand_glob(self, pattern: str) -> list[Path]:
        return []  # no files in fake workspace


class FakeSymbolStore:
    def __init__(self) -> None:
        self.explicit: list[list[str]] = []

    def add_explicit(self, symbols: list[str]) -> None:
        self.explicit.append(symbols)


# --- add file -----------------------------------------------------------------


def test_add_file_returns_message(tmp_path: Path) -> None:
    from src.cli.commands.add import run

    f = tmp_path / "engine.py"
    f.write_text("x = 1", encoding="utf-8")
    ss = FakeSecretsStore()

    result = run(str(f), Settings(workspace=tmp_path), secrets_store=ss)  # type: ignore[arg-type]

    assert isinstance(result, str)
    assert len(result) > 0


def test_add_file_calls_secrets_add_path(tmp_path: Path) -> None:
    from src.cli.commands.add import run

    f = tmp_path / "engine.py"
    f.write_text("x = 1", encoding="utf-8")
    ss = FakeSecretsStore()

    run(str(f), Settings(workspace=tmp_path), secrets_store=ss)  # type: ignore[arg-type]

    assert len(ss.added_paths) == 1


def test_add_file_message_contains_filename(tmp_path: Path) -> None:
    from src.cli.commands.add import run

    f = tmp_path / "engine.py"
    f.write_text("x = 1", encoding="utf-8")
    ss = FakeSecretsStore()

    result = run(str(f), Settings(workspace=tmp_path), secrets_store=ss)  # type: ignore[arg-type]

    assert "engine.py" in result


def test_add_nonexistent_file_raises_cli_error(tmp_path: Path) -> None:
    from src.cli.commands.add import CLIError, run

    ss = FakeSecretsStore()

    with pytest.raises(CLIError):
        run(str(tmp_path / "ghost.py"), Settings(workspace=tmp_path), secrets_store=ss)  # type: ignore[arg-type]


def test_add_nonexistent_file_does_not_write_to_store(tmp_path: Path) -> None:
    from src.cli.commands.add import CLIError, run

    ss = FakeSecretsStore()

    with pytest.raises(CLIError):
        run(str(tmp_path / "ghost.py"), Settings(workspace=tmp_path), secrets_store=ss)  # type: ignore[arg-type]

    assert ss.added_paths == []


# --- add @symbol --------------------------------------------------------------


def test_add_symbol_returns_message(tmp_path: Path) -> None:
    from src.cli.commands.add import run

    ss = FakeSecretsStore()
    sym = FakeSymbolStore()

    result = run("@RiskScorer", Settings(workspace=tmp_path), secrets_store=ss, symbol_store=sym)  # type: ignore[arg-type]

    assert isinstance(result, str)
    assert len(result) > 0


def test_add_symbol_calls_secrets_add_symbol(tmp_path: Path) -> None:
    from src.cli.commands.add import run

    ss = FakeSecretsStore()
    sym = FakeSymbolStore()

    run("@RiskScorer", Settings(workspace=tmp_path), secrets_store=ss, symbol_store=sym)  # type: ignore[arg-type]

    assert "RiskScorer" in ss.added_symbols


def test_add_symbol_calls_symbol_store_add_explicit(tmp_path: Path) -> None:
    from src.cli.commands.add import run

    ss = FakeSecretsStore()
    sym = FakeSymbolStore()

    run("@RiskScorer", Settings(workspace=tmp_path), secrets_store=ss, symbol_store=sym)  # type: ignore[arg-type]

    assert any("RiskScorer" in batch for batch in sym.explicit)


def test_add_symbol_message_contains_symbol_name(tmp_path: Path) -> None:
    from src.cli.commands.add import run

    ss = FakeSecretsStore()
    sym = FakeSymbolStore()

    result = run("@RiskScorer", Settings(workspace=tmp_path), secrets_store=ss, symbol_store=sym)  # type: ignore[arg-type]

    assert "RiskScorer" in result


def test_add_symbol_does_not_touch_paths(tmp_path: Path) -> None:
    from src.cli.commands.add import run

    ss = FakeSecretsStore()
    sym = FakeSymbolStore()

    run("@RiskScorer", Settings(workspace=tmp_path), secrets_store=ss, symbol_store=sym)  # type: ignore[arg-type]

    assert ss.added_paths == []


def test_add_file_message_contains_index_hint(tmp_path: Path) -> None:
    """Output should tell the user how to index immediately if server is not running."""
    from src.cli.commands.add import run

    f = tmp_path / "engine.py"
    f.write_text("x = 1", encoding="utf-8")
    ss = FakeSecretsStore()

    result = run(str(f), Settings(workspace=tmp_path), secrets_store=ss)  # type: ignore[arg-type]

    assert "kiri index" in result


# --- workspace fallback -------------------------------------------------------


def test_add_relative_path_resolved_from_workspace(tmp_path: Path) -> None:
    """gateway add src/engine.py works even when cwd is not the workspace root.

    Docker containers run with cwd=/app but the project is at /workspace.
    resolve_path must fall back to workspace/target when the bare relative
    path does not exist from the current directory.
    """
    from src.cli.commands.add import run

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    src = workspace / "src"
    src.mkdir()
    f = src / "engine.py"
    f.write_text("x = 1", encoding="utf-8")

    ss = FakeSecretsStore()
    sym = FakeSymbolStore()

    # Pass only the relative part — "src/engine.py" — not the absolute path.
    # From cwd (tmp_path) this does NOT exist, but from workspace it does.
    import os
    from pathlib import Path as _Path
    old_cwd = _Path.cwd()
    os.chdir(tmp_path)  # simulate /app cwd inside container
    try:
        result = run(  # type: ignore[arg-type]
            "src/engine.py", Settings(workspace=workspace),
            secrets_store=ss, symbol_store=sym,
        )
    finally:
        os.chdir(old_cwd)

    assert "engine.py" in result
    assert len(ss.added_paths) == 1


def test_add_relative_path_nonexistent_in_both_raises(tmp_path: Path) -> None:
    """If the path doesn't exist from cwd OR workspace, CLIError is raised."""
    from src.cli.commands.add import CLIError, run

    ss = FakeSecretsStore()
    sym = FakeSymbolStore()

    with pytest.raises(CLIError):
        run("ghost/engine.py", Settings(workspace=tmp_path), secrets_store=ss, symbol_store=sym)  # type: ignore[arg-type]


# --- directory → glob ---------------------------------------------------------


def test_add_directory_calls_add_glob(tmp_path: Path) -> None:
    """Passing a directory adds it as a recursive glob, not a file path."""
    from src.cli.commands.add import run

    src_dir = tmp_path / "PricingEngine"
    src_dir.mkdir()
    (src_dir / "DynamicPricer.cs").write_text("class X {}", encoding="utf-8")

    ss = FakeSecretsStore()
    sym = FakeSymbolStore()

    run("PricingEngine", Settings(workspace=tmp_path), secrets_store=ss, symbol_store=sym)  # type: ignore[arg-type]

    assert ss.added_globs == ["PricingEngine/"]
    assert ss.added_paths == []


def test_add_directory_message_contains_glob_pattern(tmp_path: Path) -> None:
    from src.cli.commands.add import run

    src_dir = tmp_path / "PricingEngine"
    src_dir.mkdir()

    ss = FakeSecretsStore()
    sym = FakeSymbolStore()

    result = run("PricingEngine", Settings(workspace=tmp_path), secrets_store=ss, symbol_store=sym)  # type: ignore[arg-type]

    assert "PricingEngine/" in result


def test_add_trailing_slash_calls_add_glob(tmp_path: Path) -> None:
    """kiri add src/engine/ (explicit trailing slash) adds a glob directly."""
    from src.cli.commands.add import run

    src_dir = tmp_path / "src" / "engine"
    src_dir.mkdir(parents=True)

    ss = FakeSecretsStore()
    sym = FakeSymbolStore()

    run("src/engine/", Settings(workspace=tmp_path), secrets_store=ss, symbol_store=sym)  # type: ignore[arg-type]

    assert ss.added_globs == ["src/engine/"]


def test_add_glob_wildcard_calls_add_glob(tmp_path: Path) -> None:
    """kiri add 'src/**/*.py' stores the glob pattern."""
    from src.cli.commands.add import run

    ss = FakeSecretsStore()
    sym = FakeSymbolStore()

    run("src/**/*.py", Settings(workspace=tmp_path), secrets_store=ss, symbol_store=sym)  # type: ignore[arg-type]

    assert ss.added_globs == ["src/**/*.py"]
    assert ss.added_paths == []


def test_add_glob_message_contains_pattern(tmp_path: Path) -> None:
    from src.cli.commands.add import run

    ss = FakeSecretsStore()
    sym = FakeSymbolStore()

    result = run("src/**/*.py", Settings(workspace=tmp_path), secrets_store=ss, symbol_store=sym)  # type: ignore[arg-type]

    assert "src/**/*.py" in result


def test_add_glob_with_real_files_reports_count(tmp_path: Path) -> None:
    """Message should report the number of currently matched files."""
    from src.cli.commands.add import run
    from src.store.secrets_store import SecretsStore

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x=1", encoding="utf-8")
    (src / "b.py").write_text("x=2", encoding="utf-8")

    secrets_file = tmp_path / ".kiri" / "secrets"
    secrets_file.parent.mkdir()
    secrets_file.touch()
    real_ss = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

    result = run("src/", Settings(workspace=tmp_path), secrets_store=real_ss)  # type: ignore[arg-type]

    assert "2 file(s)" in result
