from __future__ import annotations

import logging

from sentence_transformers import SentenceTransformer

from src.config.settings import Settings

_BATCH_SIZE = 32
# all-MiniLM-L6-v2 has a 512-token limit; ~4 chars/token → ~2048 chars is a
# rough proxy.  Inputs beyond this are silently truncated by the model.
_TRUNCATION_CHAR_LIMIT = 2048

_logger = logging.getLogger(__name__)


class Embedder:
    def __init__(self, settings: Settings) -> None:
        self._model = SentenceTransformer(settings.embedding_model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        for i, text in enumerate(texts):
            if len(text) > _TRUNCATION_CHAR_LIMIT:
                _logger.warning(
                    "embedder: text[%d] is %d chars (> %d); likely truncated by model",
                    i,
                    len(text),
                    _TRUNCATION_CHAR_LIMIT,
                )
        vectors = self._model.encode(
            texts,
            batch_size=_BATCH_SIZE,
            convert_to_numpy=True,
            normalize_embeddings=False,
        )
        return [v.tolist() for v in vectors]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
