from __future__ import annotations

from pathlib import Path

from src.config.settings import Settings

# --- fakes --------------------------------------------------------------------


class FakeSecretsStore:
    def __init__(self) -> None:
        self.removed_paths: list[Path] = []
        self.removed_symbols: list[str] = []
        self.removed_globs: list[str] = []

    def remove_path(self, path: Path) -> None:
        self.removed_paths.append(path)

    def remove_symbol(self, symbol: str) -> None:
        self.removed_symbols.append(symbol)

    def remove_glob(self, pattern: str) -> None:
        self.removed_globs.append(pattern)

    def expand_glob(self, pattern: str) -> list[Path]:
        return []

    def list_paths(self) -> list[Path]:
        return []


class FakeVectorStore:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete(self, prefix: str) -> None:
        self.deleted.append(prefix)


class FakeSymbolStore:
    def __init__(self) -> None:
        self.removed: list[str] = []

    def remove(self, source_file: str) -> None:
        self.removed.append(source_file)


# --- remove file --------------------------------------------------------------


def test_remove_file_returns_message(tmp_path: Path) -> None:
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()
    vs = FakeVectorStore()
    sym = FakeSymbolStore()
    f = tmp_path / "engine.py"

    result = run(
        str(f), Settings(workspace=tmp_path),
        secrets_store=ss, vector_store=vs, symbol_store=sym,  # type: ignore[arg-type]
    )

    assert isinstance(result, str)
    assert len(result) > 0


def test_remove_file_calls_secrets_remove_path(tmp_path: Path) -> None:
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()
    vs = FakeVectorStore()
    sym = FakeSymbolStore()
    f = tmp_path / "engine.py"

    run(str(f), Settings(workspace=tmp_path), secrets_store=ss, vector_store=vs, symbol_store=sym)  # type: ignore[arg-type]

    assert len(ss.removed_paths) == 1


def test_remove_file_purges_vector_store(tmp_path: Path) -> None:
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()
    vs = FakeVectorStore()
    sym = FakeSymbolStore()
    f = tmp_path / "engine.py"

    run(str(f), Settings(workspace=tmp_path), secrets_store=ss, vector_store=vs, symbol_store=sym)  # type: ignore[arg-type]

    assert "engine" in vs.deleted


def test_remove_file_purges_symbol_store(tmp_path: Path) -> None:
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()
    vs = FakeVectorStore()
    sym = FakeSymbolStore()
    f = tmp_path / "engine.py"

    run(str(f), Settings(workspace=tmp_path), secrets_store=ss, vector_store=vs, symbol_store=sym)  # type: ignore[arg-type]

    assert len(sym.removed) == 1


def test_remove_file_message_contains_filename(tmp_path: Path) -> None:
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()
    vs = FakeVectorStore()
    sym = FakeSymbolStore()
    f = tmp_path / "engine.py"

    result = run(  # type: ignore[arg-type]
        str(f), Settings(workspace=tmp_path),
        secrets_store=ss, vector_store=vs, symbol_store=sym,
    )

    assert "engine.py" in result


# --- remove @symbol -----------------------------------------------------------


def test_remove_symbol_returns_message(tmp_path: Path) -> None:
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()

    result = run("@RiskScorer", Settings(workspace=tmp_path), secrets_store=ss)  # type: ignore[arg-type]

    assert isinstance(result, str)


def test_remove_symbol_calls_secrets_remove_symbol(tmp_path: Path) -> None:
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()

    run("@RiskScorer", Settings(workspace=tmp_path), secrets_store=ss)  # type: ignore[arg-type]

    assert "RiskScorer" in ss.removed_symbols


def test_remove_symbol_does_not_touch_paths(tmp_path: Path) -> None:
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()

    run("@RiskScorer", Settings(workspace=tmp_path), secrets_store=ss)  # type: ignore[arg-type]

    assert ss.removed_paths == []


def test_remove_symbol_message_contains_symbol_name(tmp_path: Path) -> None:
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()

    result = run("@RiskScorer", Settings(workspace=tmp_path), secrets_store=ss)  # type: ignore[arg-type]

    assert "RiskScorer" in result


# --- path resolution ----------------------------------------------------------


def test_remove_symbol_store_key_is_resolved_absolute_path(tmp_path: Path) -> None:
    """symbol_store.remove must receive the absolute path — the watcher stores
    keys as str(resolved_path), so using the raw relative path would leave
    orphaned entries behind."""
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()
    vs = FakeVectorStore()
    sym = FakeSymbolStore()
    f = tmp_path / "engine.py"

    # Pass a relative path (simulating a CLI call from the project root)
    run(  # type: ignore[arg-type]
        str(f), Settings(workspace=tmp_path),
        secrets_store=ss, vector_store=vs, symbol_store=sym,
    )

    # The key passed to symbol_store must be the resolved absolute path
    assert len(sym.removed) == 1
    assert sym.removed[0] == str(f.resolve())


def test_remove_vector_store_uses_stem(tmp_path: Path) -> None:
    """vector_store.delete uses the file stem as doc_id prefix (matches chunk IDs)."""
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()
    vs = FakeVectorStore()
    sym = FakeSymbolStore()
    f = tmp_path / "risk_scorer.py"

    run(str(f), Settings(workspace=tmp_path), secrets_store=ss, vector_store=vs, symbol_store=sym)  # type: ignore[arg-type]

    assert "risk_scorer" in vs.deleted


# --- remove glob --------------------------------------------------------------


def test_remove_glob_trailing_slash_calls_remove_glob(tmp_path: Path) -> None:
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()
    vs = FakeVectorStore()
    sym = FakeSymbolStore()

    run(  # type: ignore[arg-type]
        "src/engine/", Settings(workspace=tmp_path), secrets_store=ss, vector_store=vs, symbol_store=sym
    )

    assert ss.removed_globs == ["src/engine/"]
    assert ss.removed_paths == []


def test_remove_glob_wildcard_calls_remove_glob(tmp_path: Path) -> None:
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()
    vs = FakeVectorStore()
    sym = FakeSymbolStore()

    run(  # type: ignore[arg-type]
        "src/**/*.py", Settings(workspace=tmp_path), secrets_store=ss, vector_store=vs, symbol_store=sym
    )

    assert ss.removed_globs == ["src/**/*.py"]


def test_remove_glob_message_contains_pattern(tmp_path: Path) -> None:
    from src.cli.commands.remove import run

    ss = FakeSecretsStore()
    vs = FakeVectorStore()
    sym = FakeSymbolStore()

    result = run(  # type: ignore[arg-type]
        "src/engine/", Settings(workspace=tmp_path), secrets_store=ss, vector_store=vs, symbol_store=sym
    )

    assert "src/engine/" in result


def test_remove_glob_purges_expanded_files(tmp_path: Path) -> None:
    """Files matched by the glob must be purged from vector and symbol stores."""
    from src.cli.commands.remove import run
    from src.store.secrets_store import SecretsStore

    src = tmp_path / "src"
    src.mkdir()
    f = src / "scorer.py"
    f.write_text("x=1", encoding="utf-8")

    secrets_file = tmp_path / ".kiri" / "secrets"
    secrets_file.parent.mkdir()
    secrets_file.write_text("@glob src/\n", encoding="utf-8")
    real_ss = SecretsStore(secrets_path=secrets_file, workspace=tmp_path)

    vs = FakeVectorStore()
    sym = FakeSymbolStore()

    run(  # type: ignore[arg-type]
        "src/", Settings(workspace=tmp_path), secrets_store=real_ss, vector_store=vs, symbol_store=sym
    )

    assert "scorer" in vs.deleted
    assert any("scorer.py" in k for k in sym.removed)


# --- path resolution ----------------------------------------------------------


def test_remove_relative_path_resolved_from_workspace(tmp_path: Path) -> None:
    """gateway rm src/engine.py works even when cwd != workspace root."""
    from src.cli.commands.remove import run

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    src = workspace / "src"
    src.mkdir()
    f = src / "engine.py"
    f.write_text("x = 1", encoding="utf-8")

    ss = FakeSecretsStore()
    vs = FakeVectorStore()
    sym = FakeSymbolStore()

    import os
    from pathlib import Path as _Path
    old_cwd = _Path.cwd()
    os.chdir(tmp_path)  # simulate /app cwd
    try:
        result = run(
            "src/engine.py", Settings(workspace=workspace),
            secrets_store=ss, vector_store=vs, symbol_store=sym,  # type: ignore[arg-type]
        )
    finally:
        os.chdir(old_cwd)

    assert "engine.py" in result
    assert len(ss.removed_paths) == 1
