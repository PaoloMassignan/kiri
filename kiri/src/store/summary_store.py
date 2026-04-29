from __future__ import annotations

import json
from pathlib import Path

from src.store.atomic_write import atomic_write_json


class SummaryStore:
    """Persist Ollama-generated safe summaries for protected chunks."""

    def __init__(self, index_dir: Path) -> None:
        self._path = index_dir / "summaries.json"
        self._index_dir = index_dir

    def save(self, chunk_id: str, summary: str) -> None:
        data = self._load()
        data[chunk_id] = summary
        self._save(data)

    def get(self, chunk_id: str) -> str | None:
        return self._load().get(chunk_id)

    def has(self, chunk_id: str) -> bool:
        return chunk_id in self._load()

    def delete(self, chunk_id: str) -> None:
        data = self._load()
        if chunk_id in data:
            del data[chunk_id]
            self._save(data)

    def all_chunk_ids(self) -> list[str]:
        return list(self._load().keys())

    def _load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def _save(self, data: dict[str, str]) -> None:
        atomic_write_json(self._path, data)
