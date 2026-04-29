from __future__ import annotations

from typing import TYPE_CHECKING

from src.cli.factory import resolve_path
from src.config.settings import Settings

if TYPE_CHECKING:
    from src.indexer.watcher import Watcher


def run(
    path: str,
    settings: Settings,
) -> str:
    watcher = _build_watcher(settings)
    watcher.index_path(resolve_path(path, settings))
    return f"Indexed {path}"


def run_all(settings: Settings) -> str:
    watcher = _build_watcher(settings)
    paths = watcher.list_protected_paths()
    if not paths:
        return "No protected files in secrets — nothing to index."

    indexed: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []

    for p in paths:
        if not p.exists():
            missing.append(p.name)
            continue
        if watcher.is_indexed(p):
            skipped.append(p.name)
            continue
        watcher.index_path(p)
        indexed.append(p.name)

    lines: list[str] = [f"Indexing {len(paths)} protected file(s)..."]
    for name in indexed:
        lines.append(f"  + {name}")
    for name in skipped:
        lines.append(f"  = {name} (already indexed, skipped)")
    for name in missing:
        lines.append(f"  ! {name} (not found, skipped)")
    lines.append("Done.")
    return "\n".join(lines)


def _build_watcher(settings: Settings) -> Watcher:
    from src.cli.factory import make_secrets_store, make_symbol_store, make_vector_store
    from src.indexer.chunker import chunk
    from src.indexer.embedder import Embedder
    from src.indexer.symbol_extractor import SymbolExtractor
    from src.indexer.watcher import Watcher

    return Watcher(
        secrets_store=make_secrets_store(settings),
        vector_store=make_vector_store(settings),
        symbol_store=make_symbol_store(settings),
        chunker=chunk,
        embedder=Embedder(settings=settings),
        extractor=SymbolExtractor(settings=settings),
    )
