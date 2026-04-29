"""Shared factory functions for CLI commands.

Store construction is centralized here to avoid repeating the same
workspace-relative path logic in every command module.
"""
from __future__ import annotations

from pathlib import Path

from src.config.settings import Settings
from src.store.secrets_store import SecretsStore
from src.store.symbol_store import SymbolStore
from src.store.vector_store import VectorStore

_KIRI_DIR = ".kiri"
_INDEX_DIR = ".kiri/index"
_SECRETS_FILE = ".kiri/secrets"


def resolve_path(target: str, settings: Settings) -> Path:
    """Resolve a CLI path argument to an absolute Path.

    Tries the path as-is first (relative to cwd, or absolute).  If that does
    not exist and the path is relative, retries relative to the workspace root.
    This lets users run ``gateway add src/engine.py`` from any directory —
    including from inside a Docker container where cwd is /app but the project
    lives at /workspace.
    """
    path = Path(target)
    if path.exists():
        return path
    if not path.is_absolute():
        workspace_path = settings.workspace / path
        if workspace_path.exists():
            return workspace_path
    return path  # return as-is so callers can produce a meaningful error


def make_secrets_store(settings: Settings) -> SecretsStore:
    return SecretsStore(
        secrets_path=settings.workspace / _SECRETS_FILE,
        workspace=settings.workspace,
    )


def make_vector_store(settings: Settings) -> VectorStore:
    return VectorStore(index_dir=settings.workspace / _INDEX_DIR)


def make_symbol_store(settings: Settings) -> SymbolStore:
    return SymbolStore(index_dir=settings.workspace / _INDEX_DIR)
