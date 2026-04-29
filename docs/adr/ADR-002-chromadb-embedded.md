# ADR-002: ChromaDB in embedded mode (no server)

## Status
Accepted

## Context

The gateway requires a vector store for the L1 similarity check.
The key requirements are:
- No additional server to install or manage
- Persists to disk (survives container restart)
- Native cosine similarity
- Simple Python interface

The gateway already runs in a Docker container. Adding a second container
(e.g. Qdrant) increases deployment complexity and introduces a dependency point
that the vector store must resolve before every query.

## Decision

Use **ChromaDB in embedded mode** (same-process, SQLite backend).

```python
import chromadb
client = chromadb.PersistentClient(path=str(index_dir / "vectors.db"))
```

Persists in `.kiri/index/vectors.db` — a Docker bind mount on the host filesystem.

## Consequences

**Positive:**
- Zero additional servers — ChromaDB runs in-process with FastAPI
- `pip install chromadb` — no infrastructure configuration
- The `.kiri/index/` file is a bind mount → persists across container restarts
- Minimal API: `add()`, `query()`, `delete()` — just a few lines of code
- Immediate startup — no health-check to wait for

**Negative:**
- Single-writer: ChromaDB embedded does not support concurrent access from multiple processes
  → acceptable because the gateway is single-process (FastAPI + indexer in the same container)
- Not scalable beyond one machine — irrelevant limitation for the onprem use case
- ChromaDB updates may change the DB format → migration required
  (acceptable: the DB is rebuildable via `kiri index --all`)

## Alternatives considered

**Qdrant (separate container):**
- Requires a second container in `docker-compose.yml`
- Adds a failure point: if Qdrant is down, the gateway must decide fail-open/closed
- Overkill for single-developer local use

**Weaviate:**
- Same problem as Qdrant + larger footprint (Java-based)

**FAISS (in-memory):**
- Does not persist to disk — every container restart requires full re-embedding
  (potentially minutes on large codebases)
- No simple update/delete API

**pgvector (PostgreSQL):**
- Requires PostgreSQL + schema migration
- Disproportionate dependency for a local vector store
