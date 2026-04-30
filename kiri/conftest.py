"""
Root conftest.py — environment setup applied before any test module is imported.

Why these env vars:
- ANONYMIZED_TELEMETRY=False  : ChromaDB fires outbound OTLP/HTTP calls during
  collection initialisation. On restricted networks or with a slow DNS these
  calls block for several seconds and make the last watcher tests appear to hang.
- TOKENIZERS_PARALLELISM=false: suppresses the HuggingFace tokenizer warning
  about forking after a parallel tokenizer has been initialised (triggered by
  sentence-transformers in the Embedder tests).
"""
from __future__ import annotations

import os

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
