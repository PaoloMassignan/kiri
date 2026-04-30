from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.store.atomic_write import atomic_write_json

_MANUAL_PREFIX = "manual__"


@dataclass
class SummaryEntry:
    text: str
    source: str          # "ollama" | "manual"
    updated_at: str      # ISO 8601 UTC
    chunk_text: str = "" # original code chunk — stored for `kiri summary reset`
    symbol_name: str = ""# primary symbol — for CLI lookup


class SummaryStore:
    """Persist summaries for protected chunks.

    Each entry carries metadata (source, updated_at, chunk_text, symbol_name)
    to support manual overrides and CLI inspection.

    Priority rule: entries with source="manual" (key prefix "manual__") take
    precedence over source="ollama" entries in the REDACT engine.
    """

    def __init__(self, index_dir: Path) -> None:
        self._path = index_dir / "summaries.json"

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(
        self,
        chunk_id: str,
        summary: str,
        *,
        chunk_text: str = "",
        symbol_name: str = "",
    ) -> None:
        """Save an Ollama-generated summary for *chunk_id*."""
        data = self._load_raw()
        data[chunk_id] = {
            "text": summary,
            "source": "ollama",
            "updated_at": _now_iso(),
            "chunk_text": chunk_text,
            "symbol_name": symbol_name,
        }
        self._persist(data)

    def set_manual(self, symbol: str, text: str) -> None:
        """Store a user-provided manual summary for *symbol*.

        Manual entries are keyed as ``manual__<symbol>`` and always take
        priority over Ollama-generated ones in the REDACT engine.
        """
        data = self._load_raw()
        data[f"{_MANUAL_PREFIX}{symbol}"] = {
            "text": text,
            "source": "manual",
            "updated_at": _now_iso(),
            "chunk_text": "",
            "symbol_name": symbol,
        }
        self._persist(data)

    def delete(self, chunk_id: str) -> None:
        data = self._load_raw()
        if chunk_id in data:
            del data[chunk_id]
            self._persist(data)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, chunk_id: str) -> str | None:
        """Return the summary text for *chunk_id*, or None. Backward-compatible."""
        entry = self.get_entry(chunk_id)
        return entry.text if entry is not None else None

    def get_entry(self, chunk_id: str) -> SummaryEntry | None:
        """Return the full SummaryEntry for *chunk_id*, or None."""
        raw = self._load_raw()
        value = raw.get(chunk_id)
        if value is None:
            return None
        return _to_entry(value)

    def has(self, chunk_id: str) -> bool:
        return chunk_id in self._load_raw()

    def find_by_symbol(self, symbol: str) -> tuple[str, SummaryEntry] | None:
        """Return the (chunk_id, SummaryEntry) whose text or symbol_name matches *symbol*.

        Manual entries are checked first (manual__ prefix), then Ollama entries.
        Returns None if no match is found.
        """
        raw = self._load_raw()

        # 1. Exact manual key
        manual_key = f"{_MANUAL_PREFIX}{symbol}"
        if manual_key in raw:
            return manual_key, _to_entry(raw[manual_key])

        # 2. Scan all entries — symbol_name field or text content
        for chunk_id, value in raw.items():
            entry = _to_entry(value)
            if entry.symbol_name == symbol or symbol in entry.text:
                return chunk_id, entry

        return None

    def all_chunk_ids(self) -> list[str]:
        return list(self._load_raw().keys())

    def all_entries(self) -> list[tuple[str, SummaryEntry]]:
        """Return all (chunk_id, SummaryEntry) pairs."""
        return [
            (chunk_id, _to_entry(value))
            for chunk_id, value in self._load_raw().items()
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_raw(self) -> dict[str, object]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def _persist(self, data: dict[str, object]) -> None:
        atomic_write_json(self._path, data)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _to_entry(value: object) -> SummaryEntry:
    """Convert a raw JSON value to SummaryEntry, migrating old string format."""
    if isinstance(value, str):
        # Pre-v0.2 format: plain string — migrate to ollama entry
        return SummaryEntry(
            text=value,
            source="ollama",
            updated_at="",
            chunk_text="",
            symbol_name="",
        )
    assert isinstance(value, dict)
    return SummaryEntry(
        text=value.get("text", ""),
        source=value.get("source", "ollama"),
        updated_at=value.get("updated_at", ""),
        chunk_text=value.get("chunk_text", ""),
        symbol_name=value.get("symbol_name", ""),
    )
