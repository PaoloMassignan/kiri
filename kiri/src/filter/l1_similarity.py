from __future__ import annotations

from dataclasses import dataclass

from src.indexer.embedder import Embedder
from src.store.vector_store import VectorStore

_TOP_K = 5


@dataclass
class L1Result:
    top_score: float
    top_doc_id: str
    top_source_file: str


class L1Filter:
    def __init__(self, vector_store: VectorStore, embedder: Embedder) -> None:
        self._vs = vector_store
        self._embedder = embedder

    def check(self, prompt: str) -> L1Result:
        vector = self._embedder.embed_one(prompt)
        results = self._vs.query(vector, top_k=_TOP_K)

        if not results:
            return L1Result(top_score=0.0, top_doc_id="", top_source_file="")

        top = results[0]
        return L1Result(
            top_score=top.similarity,
            top_doc_id=top.doc_id,
            top_source_file=top.source_file,
        )
