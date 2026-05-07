from __future__ import annotations

import logging
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver
from watchdog.observers.polling import PollingObserver

from src.config.settings import Settings
from src.indexer.chunker import Chunk, extract_numeric_constants, extract_symbols
from src.indexer.embedder import Embedder
from src.indexer.symbol_extractor import OllamaUnavailableError, SymbolExtractor
from src.redaction.summary_generator import SummaryGenerationError, SummaryGenerator
from src.store.secrets_store import InlineBlock, SecretsStore
from src.store.summary_store import SummaryStore
from src.store.symbol_store import SymbolStore
from src.store.vector_store import VectorStore

logger = logging.getLogger(__name__)


class Watcher:
    def __init__(
        self,
        secrets_store: SecretsStore,
        vector_store: VectorStore,
        symbol_store: SymbolStore,
        chunker: Callable[[Path], list[Chunk]],
        embedder: Embedder,
        extractor: SymbolExtractor,
        summary_generator: SummaryGenerator | None = None,
        summary_store: SummaryStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._secrets = secrets_store
        self._vs = vector_store
        self._ss = symbol_store
        self._chunker = chunker
        self._embedder = embedder
        self._extractor = extractor
        self._summary_generator = summary_generator
        self._summary_store = summary_store
        self._settings = settings or Settings()
        self._known_paths: set[Path] = set()
        self._known_glob_rules: set[str] = set()
        self._glob_expanded: dict[str, set[Path]] = {}
        self._observer: BaseObserver | None = None
        self._glob_rescan_interval: int = 60

    def _store_embedded_chunks(
        self,
        chunks: list[Chunk],
        vectors: list[Any],
        *,
        doc_id_prefix: str | None = None,
        source_key: str | None = None,
    ) -> None:
        """Add *chunks* to the vector store and optionally generate summaries.

        *doc_id_prefix*: when set, the doc_id for each chunk is
            ``{prefix}__{chunk.chunk_index}`` instead of ``chunk.doc_id``.
        *source_key*: when set, overrides ``chunk.source_file`` in metadata.
        """
        for chunk, vector in zip(chunks, vectors, strict=False):
            doc_id = f"{doc_id_prefix}__{chunk.chunk_index}" if doc_id_prefix else chunk.doc_id
            file_key = source_key or chunk.source_file
            self._vs.add(
                doc_id, vector,
                {"source_file": file_key, "chunk_index": str(chunk.chunk_index)},
            )
            if self._summary_generator is not None and self._summary_store is not None:
                symbol_name = chunk.name or doc_id
                # Generate summaries for all indexed chunks.
                # A developer debugging code that calls internal helpers benefits from
                # knowing what _calculateRaw or _calibrate do. The summary is safe by
                # design (Ollama is local, and the prompt explicitly forbids revealing
                # algorithms or magic numbers).
                try:
                    summary = self._summary_generator.generate(doc_id, chunk.text, symbol_name)
                    self._summary_store.save(
                        doc_id,
                        summary,
                        chunk_text=chunk.text,
                        symbol_name=symbol_name,
                    )
                except SummaryGenerationError:
                    logger.warning("watcher: summary generation failed for chunk %s", doc_id)

    def index_path(self, path: Path) -> None:
        if not path.exists():
            logger.warning("watcher: skipping missing file %s", path)
            return
        if not path.is_file():
            logger.warning("watcher: skipping non-file path %s", path)
            return

        chunks = self._chunker(path)
        if not chunks:
            return

        vectors = self._embedder.embed([c.text for c in chunks])
        self._store_embedded_chunks(chunks, vectors)

        # Chunk names (tree-sitter method/class names) are always domain-specific
        # by definition — if the chunker gave it a name, it is a named symbol in
        # the protected file.  Seed the confirmed set unconditionally.
        chunk_names = [c.name for c in chunks if c.name]
        confirmed: list[str] = list(chunk_names)
        if chunk_names:
            logger.debug(
                "watcher: %d chunk names pinned for %s: %s",
                len(chunk_names), path.name, chunk_names,
            )

        # extract_symbols walks the full AST including module-level variables,
        # which chunk() omits (it only creates chunks for functions/classes).
        # Run Ollama filtering only on the remaining AST symbols (constants,
        # top-level vars, etc.) that chunk_names did not already cover.
        ast_symbols = extract_symbols(path, min_length=self._settings.symbol_min_length)
        if ast_symbols:
            remaining = [s for s in ast_symbols if s not in chunk_names]
            if remaining:
                # Ask Ollama to filter out generic programming terms, keeping only
                # domain-specific symbols. Falls back to all remaining symbols if unavailable.
                try:
                    filtered = self._extractor.filter_symbols(remaining, path)
                    logger.debug(
                        "watcher: symbol filter %s → %d/%d kept",
                        path.name, len(filtered), len(remaining),
                    )
                    confirmed.extend(filtered)
                except OllamaUnavailableError:
                    logger.warning(
                        "watcher: Ollama unavailable — using all AST symbols for %s", path
                    )
                    confirmed.extend(remaining)
            if confirmed:
                self._ss.add(str(path), confirmed)
            numeric_constants = extract_numeric_constants(path)
            if numeric_constants:
                self._ss.add_numbers(str(path), numeric_constants)
        elif confirmed:
            # No AST symbols (unsupported language) but chunk names were found
            self._ss.add(str(path), confirmed)
        else:
            # Fallback to Ollama for unsupported file types
            full_text = "\n\n".join(c.text for c in chunks)
            try:
                symbols = self._extractor.extract(full_text)
                self._ss.add(str(path), symbols)
            except OllamaUnavailableError:
                logger.warning(
                    "watcher: Ollama unavailable — skipping symbol extraction for %s", path
                )

    def index_subfile(self, path: Path, symbol: str) -> None:
        """Index only the chunk matching *symbol* from *path* (US-1)."""
        if not path.exists():
            logger.warning("watcher: skipping missing file %s", path)
            return

        all_chunks = self._chunker(path)
        # keep only the chunk whose name matches the requested symbol
        chunks = [c for c in all_chunks if c.name == symbol]
        if not chunks:
            logger.warning("watcher: symbol %r not found in %s", symbol, path)
            return

        texts = [c.text for c in chunks]
        vectors = self._embedder.embed(texts)
        for chunk, vector in zip(chunks, vectors, strict=False):
            self._vs.add(
                chunk.doc_id,
                vector,
                {"source_file": chunk.source_file, "chunk_index": str(chunk.chunk_index)},
            )

        # Register the symbol name directly — no need for full AST walk
        self._ss.add(f"{path}::{symbol}", [symbol])

    def index_inline_block(self, block: InlineBlock) -> None:
        """Index an inline block defined directly in the secrets file (US-2)."""
        key = f"@inline:{block.name}"
        doc_id_prefix = f"@inline_{block.name}"

        # Write content to a temp .py file so the chunker + extractors can parse it
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", encoding="utf-8", delete=False
        ) as fh:
            fh.write(block.content)
            tmp_path = Path(fh.name)

        try:
            chunks = self._chunker(tmp_path)
            if not chunks:
                chunks = [
                    Chunk(
                        doc_id=f"{doc_id_prefix}__0",
                        text=block.content.strip(),
                        source_file=key,
                        chunk_index=0,
                    )
                ]

            vectors = self._embedder.embed([c.text for c in chunks])
            self._store_embedded_chunks(
                chunks, vectors, doc_id_prefix=doc_id_prefix, source_key=key
            )

            ast_symbols = extract_symbols(tmp_path)
            if ast_symbols:
                self._ss.add(key, ast_symbols)

            numeric = extract_numeric_constants(tmp_path)
            if numeric:
                self._ss.add_numbers(key, numeric)
        finally:
            tmp_path.unlink(missing_ok=True)

    def list_protected_paths(self) -> list[Path]:
        """Return all paths currently listed in the secrets file."""
        return self._secrets.list_paths()

    def is_indexed(self, path: Path) -> bool:
        """Return True if *path* has at least one chunk in the vector store."""
        return self._vs.count_prefix(path.stem) > 0

    def purge_path(self, path: Path) -> None:
        self._vs.delete(path.stem)
        self._ss.remove(str(path))

    def initial_scan(self) -> None:
        """Index all paths and glob rules in secrets that are not yet in VectorStore.

        Already-indexed files are skipped to avoid unnecessary re-embedding.
        Missing files are logged as warnings and skipped — they do not block startup.
        """
        for path in self._secrets.list_paths():
            if not path.exists():
                logger.warning("initial_scan: file not found: %s", path)
                continue
            if self._vs.count_prefix(path.stem) > 0:
                logger.debug("initial_scan: already indexed, skipping %s", path.name)
                continue
            logger.info("initial_scan: indexing %s", path.name)
            self.index_path(path)

        for pattern in self._secrets.list_glob_rules():
            files = set(self._secrets.expand_glob(pattern))
            for path in files:
                if not path.exists():
                    logger.warning("initial_scan: file not found: %s (glob '%s')", path, pattern)
                    continue
                if self._vs.count_prefix(path.stem) > 0:
                    logger.debug("initial_scan: already indexed, skipping %s", path.name)
                    continue
                logger.info("initial_scan: indexing %s (glob '%s')", path.name, pattern)
                self.index_path(path)
            self._glob_expanded[pattern] = files

    def start(self) -> None:
        self.initial_scan()
        self._known_paths = set(self._secrets.list_paths())
        self._known_glob_rules = set(self._secrets.list_glob_rules())

        secrets_path = self._secrets.secrets_path
        handler = _SecretsEventHandler(secrets_path.name, self._on_secrets_changed)

        # On Docker Desktop (Windows/macOS) with bind-mounted volumes, the native
        # observer (inotify on Linux) starts without error but never receives
        # events — the host filesystem changes don't propagate to the container's
        # inotify.  Detect this case by checking for the Docker environment file
        # and fall back to PollingObserver (polls every 1 s, works everywhere).
        # On native Linux the native observer is used — zero-CPU when idle.
        if _is_docker():
            observer: BaseObserver = PollingObserver(timeout=1)
            logger.debug("watcher: Docker detected — using PollingObserver (1 s interval)")
        else:
            observer = Observer()
            logger.debug("watcher: using native observer for %s", secrets_path.parent)

        observer.schedule(handler, str(secrets_path.parent), recursive=False)
        observer.daemon = True
        observer.start()
        self._observer = observer

        self._start_glob_rescan_thread()

    def stop(self) -> None:
        if self._observer is not None and self._observer.is_alive():
            self._observer.stop()
            self._observer.join()

    def _on_secrets_changed(self) -> None:
        new_paths = set(self._secrets.list_paths())
        added = new_paths - self._known_paths
        removed = self._known_paths - new_paths

        for path in added:
            self.index_path(path)
        for path in removed:
            self.purge_path(path)

        self._known_paths = new_paths

        # Handle glob rule changes
        new_glob_rules = set(self._secrets.list_glob_rules())
        added_globs = new_glob_rules - self._known_glob_rules
        removed_globs = self._known_glob_rules - new_glob_rules

        for pattern in added_globs:
            files = set(self._secrets.expand_glob(pattern))
            for path in files:
                self.index_path(path)
            self._glob_expanded[pattern] = files
            logger.info("watcher: glob added '%s' — %d file(s) indexed", pattern, len(files))

        for pattern in removed_globs:
            files = self._glob_expanded.pop(pattern, set())
            for path in files:
                if path not in new_paths:
                    self.purge_path(path)
            logger.info("watcher: glob removed '%s' — %d file(s) purged", pattern, len(files))

        self._known_glob_rules = new_glob_rules

    def _start_glob_rescan_thread(self) -> None:
        def rescan_loop() -> None:
            while True:
                time.sleep(self._glob_rescan_interval)
                try:
                    self._rescan_globs()
                except Exception:
                    logger.exception("watcher: error during glob rescan")

        t = threading.Thread(target=rescan_loop, daemon=True, name="kiri-glob-rescan")
        t.start()

    def _rescan_globs(self) -> None:
        """Re-expand active glob rules; index new files and purge removed files."""
        individual_paths = set(self._secrets.list_paths())
        for pattern in list(self._known_glob_rules):
            current_files = set(self._secrets.expand_glob(pattern))
            previous_files = self._glob_expanded.get(pattern, set())

            for path in current_files - previous_files:
                logger.info("watcher: new file matched glob '%s': %s", pattern, path.name)
                self.index_path(path)

            for path in previous_files - current_files:
                if path not in individual_paths:
                    logger.info("watcher: file removed from glob '%s': %s", pattern, path.name)
                    self.purge_path(path)

            self._glob_expanded[pattern] = current_files


def _is_docker() -> bool:
    """Return True when running inside a Docker container.

    Docker injects /.dockerenv into every container.  This is the canonical
    lightweight check — no subprocess, no env-var dependency.
    """
    return Path("/.dockerenv").exists()


class _SecretsEventHandler(FileSystemEventHandler):
    def __init__(self, filename: str, callback: Callable[[], None]) -> None:
        super().__init__()
        self._filename = filename
        self._callback = callback

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory and Path(str(event.src_path)).name == self._filename:
            self._callback()

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory and Path(str(event.src_path)).name == self._filename:
            self._callback()
