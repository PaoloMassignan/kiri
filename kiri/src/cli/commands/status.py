from __future__ import annotations

from src.cli.factory import make_secrets_store, make_symbol_store, make_vector_store
from src.config.settings import Settings
from src.store.secrets_store import SecretsStore
from src.store.symbol_store import SymbolStore
from src.store.vector_store import VectorStore


def run(
    settings: Settings,
    *,
    secrets_store: SecretsStore | None = None,
    vector_store: VectorStore | None = None,
    symbol_store: SymbolStore | None = None,
) -> str:
    if secrets_store is None:
        secrets_store = make_secrets_store(settings)
    if vector_store is None:
        vector_store = make_vector_store(settings)
    if symbol_store is None:
        symbol_store = make_symbol_store(settings)

    paths = secrets_store.list_paths()
    symbols = secrets_store.list_symbols()
    chunk_count = vector_store.count()
    symbol_count = len(symbol_store.all_symbols())

    lines: list[str] = ["=== Gateway Protection Status ==="]

    lines.append(f"\nProtected files ({len(paths)}):")
    if paths:
        for p in paths:
            lines.append(f"  {p}")
    else:
        lines.append("  (none)")

    lines.append(f"\nExplicit symbols ({len(symbols)}):")
    if symbols:
        for s in symbols:
            lines.append(f"  @{s}")
    else:
        lines.append("  (none)")

    lines.append(f"\nIndexed chunks : {chunk_count}")
    lines.append(f"Known symbols  : {symbol_count}")

    return "\n".join(lines)
