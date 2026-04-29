# Non-Functional Requirements — EARS Format

Requirements ID prefix: `REQ-NF-`

---

## REQ-NF-001: Added latency (critical path)

```
WHILE the L1 similarity score is above 0.90 or below 0.75,
the gateway SHALL add no more than 20ms of latency
to the time-to-first-token of the upstream response.
```

**Rationale:** L2 and L3 are only invoked in the grace zone (5–15% of requests).
The fast path (L1 only) must be imperceptible to developers.

---

## REQ-NF-002: Fail-open on internal errors

```
IF the vector store (ChromaDB) returns an error during L1 query,
THEN the gateway SHALL treat the result as PASS and forward the request.

IF the Ollama classifier (L3) does not respond within the timeout,
THEN the gateway SHALL treat the result as PASS and forward the request.
```

**ADR:** [ADR-004](../adr/ADR-004-fail-open.md)
**Rationale:** developer productivity is never blocked by gateway infrastructure failures.

---

## REQ-NF-003: Persistence after restart

```
WHILE the gateway container is restarted,
the gateway SHALL retain all protected paths, symbols, indexed vectors,
audit log entries, and kiri keys without requiring re-configuration.
```

**Rationale:** `.kiri/` is a Docker bind mount on the host filesystem.
Vectors, keys, and audit log survive container restarts.

---

## REQ-NF-004: Offline operation

```
WHILE no internet connection is available,
the gateway SHALL continue to filter, block, and forward requests
using locally cached models (sentence-transformers, Ollama qwen2.5:3b).
```

**Rationale:** developer machines may work offline or in restricted network environments.
The embedding model and Ollama classifier must not require network access at runtime.

---

## REQ-NF-005: No source code copy outside the perimeter

```
The gateway SHALL NOT transmit source code to any external API.
The gateway SHALL NOT store source code in the vector index —
only float[] embedding vectors (non-invertible) and symbol names.
```

**Rationale:** core privacy guarantee of the product.
**Verification:** data flow analysis in [`../sdd/02-architecture.md`](../sdd/02-architecture.md)
section "Data flow — no-code-in-cloud guarantee".

---

## REQ-NF-006: Single host dependency

```
The gateway SHALL require only Docker Desktop installed on the host system.
All other dependencies (Python, Ollama, ChromaDB, sentence-transformers, models)
SHALL be packaged inside the Docker image.
```

**Rationale:** zero-friction developer onboarding — one install, then transparent operation.

---

## REQ-NF-007: Configuration sharing via git

```
The gateway SHALL store protection policy (.kiri/secrets, .kiri/config.yaml)
in files suitable for git commit and team-wide sharing.
The gateway SHALL NOT require any out-of-band configuration channel
for new developers joining a project.
```

**Rationale:** L2 protection (symbol matching) becomes active immediately on `git pull`,
before any local re-indexing. New developers are protected from the first pull.
