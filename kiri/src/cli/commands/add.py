from __future__ import annotations

from pathlib import Path

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

    # Explicit glob: contains wildcard or trailing path separator
    if "*" in target or target.endswith("/") or target.endswith("\\"):
        pattern = _normalise_glob(target, settings)
        return _add_glob(pattern, secrets_store)

    path = resolve_path(target, settings)
    if not path.exists():
        raise CLIError(f"Path does not exist: {target}")

    # Directory without explicit trailing slash → treat as recursive glob
    if path.is_dir():
        rel = str(path.relative_to(Path(settings.workspace).resolve()))
        pattern = rel.replace("\\", "/") + "/"
        return _add_glob(pattern, secrets_store)

    secrets_store.add_path(path)
    hint = " (run 'kiri index' to index now if server is not running)"
    return f"Added {path.name} to protected files{hint}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_glob(target: str, settings: Settings) -> str:
    """Return a workspace-relative glob pattern with forward slashes."""
    workspace = Path(settings.workspace).resolve()
    # Strip trailing separators only when the target has no wildcard
    # (so trailing-slash directory rules keep their slash)
    raw = target.replace("\\", "/")
    # If absolute, make workspace-relative
    try:
        abs_path = Path(raw.rstrip("/"))
        if abs_path.is_absolute():
            rel = str(abs_path.relative_to(workspace))
            if raw.endswith("/"):
                return rel.replace("\\", "/") + "/"
            return rel.replace("\\", "/")
    except ValueError:
        pass
    return raw


def _add_glob(pattern: str, secrets_store: SecretsStore) -> str:
    secrets_store.add_glob(pattern)
    expanded = secrets_store.expand_glob(pattern)
    count = len(expanded)
    hint = " (run 'kiri index' to index now if server is not running)"
    if count == 0:
        return f"Added glob '{pattern}' — no files matched yet{hint}"
    return f"Added glob '{pattern}' — {count} file(s) matched{hint}"
