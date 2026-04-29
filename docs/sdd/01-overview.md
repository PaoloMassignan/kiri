# SDD-01: System Overview

## Purpose

Kiri is a local HTTP proxy that intercepts all calls
to cloud LLMs (Anthropic Claude, OpenAI GPT) and prevents proprietary source code
from leaving the corporate network.

**Problem solved:** developers use AI tools (Claude Code, Cursor, Copilot)
that send source code to external cloud servers. If the code contains
proprietary algorithms, corporate IP, or sensitive data, this creates an
uncontrollable exposure risk.

**Approach:** the gateway inserts itself into the path of every LLM call,
analyzes the prompt locally using on-prem models, and decides PASS/BLOCK/REDACT
before any data leaves the developer's machine.

---

## Design principles

### 1. Full transparency for the developer
The developer does not need to change anything in their workflow. They set `ANTHROPIC_BASE_URL`
once, then forget the gateway exists. All tools (Claude Code,
Cursor, Copilot) continue to work identically.

### 2. Fail-open
A gateway that blocks work due to an infrastructure problem gets disabled.
Internal errors (DB, classifier) → PASS, not BLOCK. See [ADR-004](../adr/ADR-004-fail-open.md).

### 3. No code in cloud
The gateway never sends source code to external servers. Only floating-point vectors
(non-invertible) are produced by the indexing process. See [SDD-06](06-security.md).

### 4. Immediate protection via symbols
A new developer who does `git pull` has L2 protection (symbol matching) active
immediately, before any reindex. Critical symbols travel in `secrets`
committed to the repo. See [ADR-001](../adr/ADR-001-filter-3-levels.md).

### 5. Configuration via git
Protection policies (`.kiri/secrets`, `.kiri/config.yaml`) are files
committed to the repository. A `git pull` automatically synchronizes policies
across all team developers.

---

## Main components

| Component | Responsibility | File |
|-----------|---------------|------|
| HTTP Proxy | Intercepts LLM calls | `src/proxy/server.py` |
| Filter Pipeline | L1/L2/L3 decision | `src/filter/pipeline.py` |
| Indexer | Produces vectors and symbols from source files | `src/indexer/` |
| File Watcher | Monitors `secrets`, triggers reindex | `src/indexer/watcher.py` |
| CLI | Commands `kiri add/rm/status/inspect/log` | `src/cli/` |
| Stores | Persistence (secrets, vectors, symbols, audit) | `src/store/` |
| Key Manager | Authentication and `kr-` key management | `src/keys/manager.py` |
| Audit Log | Persistent record of every decision | `src/audit/log.py` |

---

## Deployment

The gateway runs in a **local Docker container** with `restart: always`.
It mounts the project directory as a read-only volume, with `.kiri/` in read-write.

```
Host filesystem:
  /project/
    src/                  ← source code (ro in container)
    .kiri/
      secrets             ← policy (rw, committed)
      config.yaml         ← configuration (rw, committed)
      upstream.key        ← Anthropic key (rw, NOT committed)
      index/              ← vectors (rw, NOT committed)
      audit.log           ← log (rw, NOT committed)
      keys/               ← kr- keys (rw, NOT committed)
```

Single dependency on the host system: **Docker Desktop**.
Everything else (Python, models, ChromaDB) is inside the Docker image.

---

## Relationship to requirements

| Principle | Requirements | ADR |
|-----------|-----------|-----|
| Transparency | REQ-NF-001, REQ-NF-006 | — |
| Fail-open | REQ-NF-002 | ADR-004 |
| No-code-in-cloud | REQ-NF-005 | — |
| Immediate protection | REQ-F-002, REQ-NF-007 | ADR-001 |
| Config via git | REQ-NF-007 | — |
