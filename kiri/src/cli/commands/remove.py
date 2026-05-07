from __future__ import annotations

from pathlib import Path

from src.cli.factory import make_secrets_store, make_symbol_store, make_vector_store, resolve_path
from src.config.settings import Settings
from src.store.secrets_store import SecretsStore
from src.store.symbol_store import SymbolStore
from src.store.vector_store import VectorStore


class CLIError(Exception):
    pass


def run(
    target: str,
    settings: Settings,
    *,
    secrets_store: SecretsStore | None = None,
    vector_store: VectorStore | None = None,
    symbol_store: SymbolStore | None = None,
) -> str:
    if secrets_store is None:
        secrets_store = make_secrets_store(settings)

    if target.startswith("@"):
        symbol = target.removeprefix("@").strip()
        secrets_store.remove_symbol(symbol)
        return f"Removed @{symbol} from protected symbols"

    # Explicit glob: contains wildcard or trailing path separator
    if "*" in target or target.endswith("/") or target.endswith("\\"):
        pattern = target.replace("\\", "/")
        if vector_store is None:
            vector_store = make_vector_store(settings)
        if symbol_store is None:
            symbol_store = make_symbol_store(settings)
        return _remove_glob(pattern, secrets_store, vector_store, symbol_store)

    path = resolve_path(target, settings)

    # If the resolved path is a directory, treat as glob removal
    if path.is_dir():
        rel = str(path.relative_to(Path(settings.workspace).resolve()))
        pattern = rel.replace("\\", "/") + "/"
        if vector_store is None:
            vector_store = make_vector_store(settings)
        if symbol_store is None:
            symbol_store = make_symbol_store(settings)
        return _remove_glob(pattern, secrets_store, vector_store, symbol_store)

    secrets_store.remove_path(path)

    if vector_store is None:
        vector_store = make_vector_store(settings)
    if symbol_store is None:
        symbol_store = make_symbol_store(settings)

    # Resolve to absolute path — the watcher stores symbol keys as absolute strings.
    # Using the raw relative path would leave orphaned entries in the symbol store.
    resolved = path.resolve()
    vector_store.delete(resolved.stem)
    symbol_store.remove(str(resolved))
    return f"Removed {path.name} from protected files"


def _remove_glob(
    pattern: str,
    secrets_store: SecretsStore,
    vector_store: VectorStore,
    symbol_store: SymbolStore,
) -> str:
    # Expand before removing so we know which files to purge
    expanded = secrets_store.expand_glob(pattern)
    secrets_store.remove_glob(pattern)

    # Don't purge files that are also individually protected
    individual_paths = set(secrets_store.list_paths())

    purged = 0
    for path in expanded:
        if path not in individual_paths:
            vector_store.delete(path.stem)
            symbol_store.remove(str(path))
            purged += 1

    if not expanded:
        return f"Removed glob '{pattern}'"
    return f"Removed glob '{pattern}' — purged {purged} file(s) from index"
