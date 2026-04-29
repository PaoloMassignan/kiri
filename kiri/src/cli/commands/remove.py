from __future__ import annotations

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

    path = resolve_path(target, settings)
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
