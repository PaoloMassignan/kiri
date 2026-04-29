# Key Decisions

Quick-reference for the non-obvious design choices in this codebase.
Full rationale, alternatives considered, and consequences in [`docs/adr/`](docs/adr/).

---

| # | Decision | Why | Full ADR |
|---|----------|-----|----------|
| 1 | **Three-level filter (L1+L2+L3)** | A single classifier has either too much latency or too many false positives. The grace zone (0.75–0.90) applies L2+L3 only on ambiguous cases (~10% of requests). | [ADR-001](docs/adr/ADR-001-filter-3-levels.md) |
| 2 | **ChromaDB embedded, no server** | Zero extra container, persists on disk as a bind mount, zero ops. Qdrant/Weaviate are overkill for single-developer local use. | [ADR-002](docs/adr/ADR-002-chromadb-embedded.md) |
| 3 | **Upstream API key via Docker secret, not env var** | `docker inspect` exposes env vars. A Docker secret file is not visible to `docker inspect` or `docker exec env`. | [ADR-003](docs/adr/ADR-003-docker-secrets.md) |
| 4 | **Fail-open on L1/L3 errors** ⚠️ | A gateway that blocks work due to infrastructure failures gets disabled. L2 (symbol match) is always active as safety net. **Do not change to fail-closed.** | [ADR-004](docs/adr/ADR-004-fail-open.md) |
| 5 | **Two-key model (kr- + sk-ant-)** | Developer has a `kr-` key that only works with the gateway. Using it directly against Anthropic returns 401 — bypass is impossible without the real key. | [ADR-005](docs/adr/ADR-005-gateway-key-model.md) |
| 6 | **REDACT instead of BLOCK in grace zone** | Lets developers ask about *how to use* a protected function without exposing the implementation. Reduces false positives that would erode trust in the gateway. | [ADR-006](docs/adr/ADR-006-redact-vs-block.md) |
| 8 | **REDACT as default — BLOCK only on explicit L3 extraction intent** | BLOCK and REDACT protect IP equally. BLOCK adds friction without security gain. BLOCK is reserved for when L3 detects deliberate extraction intent. | [ADR-008](docs/adr/ADR-008-redact-as-default.md) |
| 7 | **EARS format for requirements** | Structured English with explicit trigger/condition/action. Requirements are unambiguous, testable, and traceable to code. | [ADR-007](docs/adr/ADR-007-ears-requirements.md) |
