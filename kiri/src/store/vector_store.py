from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from chromadb import Collection

_COLLECTION = "gateway_index"


@dataclass
class QueryResult:
    doc_id: str
    similarity: float
    source_file: str
    chunk_index: int


class VectorStore:
    def __init__(self, index_dir: Path) -> None:
        index_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(index_dir / "vectors.db"))
        self._col: Collection = self._get_or_create_collection()

    def add(self, doc_id: str, vector: list[float], metadata: dict[str, str]) -> None:
        self._col.upsert(
            ids=[doc_id],
            embeddings=[vector],  # type: ignore[arg-type]
            metadatas=[metadata],
        )

    def query(self, vector: list[float], top_k: int) -> list[QueryResult]:
        n = min(top_k, self._col.count())
        if n == 0:
            return []

        raw: Any = self._col.query(
            query_embeddings=[vector],  # type: ignore[arg-type]
            n_results=n,
            include=["distances", "metadatas"],  # type: ignore[list-item]
        )

        ids: list[str] = raw["ids"][0]
        distances: list[float] = raw["distances"][0]
        metadatas: list[dict[str, str]] = raw["metadatas"][0]

        results = []
        for doc_id, distance, meta in zip(ids, distances, metadatas, strict=False):
            # ChromaDB cosine distance ∈ [0, 2]: 0 = identical, 2 = opposite
            similarity = 1.0 - (distance / 2.0)
            results.append(QueryResult(
                doc_id=doc_id,
                similarity=round(similarity, 6),
                source_file=meta["source_file"],
                chunk_index=int(meta["chunk_index"]),
            ))

        return results

    def delete(self, doc_id_prefix: str) -> None:
        all_ids = self._col.get(include=[])["ids"]
        targets = [id_ for id_ in all_ids if id_.startswith(doc_id_prefix + "__")]
        if targets:
            self._col.delete(ids=targets)

    def count(self) -> int:
        return self._col.count()

    def count_prefix(self, prefix: str) -> int:
        """Return the number of stored vectors whose ID starts with *prefix*__."""
        all_ids = self._col.get(include=[])["ids"]
        return sum(1 for id_ in all_ids if id_.startswith(prefix + "__"))

    def reset(self) -> None:
        self._client.delete_collection(_COLLECTION)
        self._col = self._get_or_create_collection()

    def _get_or_create_collection(self) -> Collection:
        return self._client.get_or_create_collection(
            name=_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
