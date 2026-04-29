from __future__ import annotations

from src.cli.factory import make_secrets_store, make_symbol_store, resolve_path
from src.config.settings import Settings
from src.store.secrets_store import SecretsStore
from src.store.symbol_store import SymbolStore


class CLIError(Exception):
    pass


def run(
    target: str,
    settings: Settings,
    *,
    secrets_store: SecretsStore | None = None,
    symbol_store: SymbolStore | None = None,
) -> str:
    if secrets_store is None:
        secrets_store = make_secrets_store(settings)
    if symbol_store is None:
        symbol_store = make_symbol_store(settings)

    if target.startswith("@"):
        symbol = target.removeprefix("@").strip()
        secrets_store.add_symbol(symbol)
        symbol_store.add_explicit([symbol])
        return f"Added @{symbol} to protected symbols"

    path = resolve_path(target, settings)
    if not path.exists():
        raise CLIError(f"Path does not exist: {target}")
    if path.is_dir():
        files = [f.name for f in path.iterdir() if f.is_file()]
        examples = ", ".join(files[:3]) + ("..." if len(files) > 3 else "")
        hint = f" e.g. 'kiri add {path.name}/{files[0]}'" if files else ""
        raise CLIError(
            f"{target} is a directory — add individual files instead.{hint}"
        )
    secrets_store.add_path(path)
    # Hint: indexing is handled automatically by the watcher when the gateway
    # is running.  If the server is not running yet, use `kiri index <path>`
    # to build the embedding index immediately.
    hint = " (run 'kiri index' to index now if server is not running)"
    return f"Added {path.name} to protected files{hint}"
