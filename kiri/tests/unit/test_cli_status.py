from __future__ import annotations

from pathlib import Path

from src.config.settings import Settings

# --- fakes --------------------------------------------------------------------


class FakeSecretsStore:
    def __init__(
        self,
        paths: list[Path] | None = None,
        symbols: list[str] | None = None,
    ) -> None:
        self._paths = paths or []
        self._symbols = symbols or []

    def list_paths(self) -> list[Path]:
        return list(self._paths)

    def list_symbols(self) -> list[str]:
        return list(self._symbols)


class FakeVectorStore:
    def __init__(self, count: int = 0) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class FakeSymbolStore:
    def __init__(self, symbols: set[str] | None = None) -> None:
        self._symbols = symbols or set()

    def all_symbols(self) -> set[str]:
        return set(self._symbols)


# --- status output ------------------------------------------------------------


def test_status_returns_string(tmp_path: Path) -> None:
    from src.cli.commands.status import run

    result = run(
        Settings(workspace=tmp_path),
        secrets_store=FakeSecretsStore(),  # type: ignore[arg-type]
        vector_store=FakeVectorStore(),  # type: ignore[arg-type]
        symbol_store=FakeSymbolStore(),  # type: ignore[arg-type]
    )

    assert isinstance(result, str)


def test_status_lists_protected_files(tmp_path: Path) -> None:
    from src.cli.commands.status import run

    f = tmp_path / "engine.py"
    result = run(
        Settings(workspace=tmp_path),
        secrets_store=FakeSecretsStore(paths=[f]),  # type: ignore[arg-type]
        vector_store=FakeVectorStore(),  # type: ignore[arg-type]
        symbol_store=FakeSymbolStore(),  # type: ignore[arg-type]
    )

    assert "engine.py" in result


def test_status_lists_explicit_symbols(tmp_path: Path) -> None:
    from src.cli.commands.status import run

    result = run(
        Settings(workspace=tmp_path),
        secrets_store=FakeSecretsStore(symbols=["RiskScorer"]),  # type: ignore[arg-type]
        vector_store=FakeVectorStore(),  # type: ignore[arg-type]
        symbol_store=FakeSymbolStore(),  # type: ignore[arg-type]
    )

    assert "RiskScorer" in result


def test_status_shows_chunk_count(tmp_path: Path) -> None:
    from src.cli.commands.status import run

    result = run(
        Settings(workspace=tmp_path),
        secrets_store=FakeSecretsStore(),  # type: ignore[arg-type]
        vector_store=FakeVectorStore(count=42),  # type: ignore[arg-type]
        symbol_store=FakeSymbolStore(),  # type: ignore[arg-type]
    )

    assert "42" in result


def test_status_shows_symbol_count(tmp_path: Path) -> None:
    from src.cli.commands.status import run

    result = run(
        Settings(workspace=tmp_path),
        secrets_store=FakeSecretsStore(),  # type: ignore[arg-type]
        vector_store=FakeVectorStore(),  # type: ignore[arg-type]
        symbol_store=FakeSymbolStore(symbols={"Foo", "Bar", "Baz"}),  # type: ignore[arg-type]
    )

    assert "3" in result


def test_status_empty_shows_nothing_protected(tmp_path: Path) -> None:
    from src.cli.commands.status import run

    result = run(
        Settings(workspace=tmp_path),
        secrets_store=FakeSecretsStore(),  # type: ignore[arg-type]
        vector_store=FakeVectorStore(count=0),  # type: ignore[arg-type]
        symbol_store=FakeSymbolStore(),  # type: ignore[arg-type]
    )

    assert "0" in result
