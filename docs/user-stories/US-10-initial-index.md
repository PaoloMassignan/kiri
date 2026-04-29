# US-10 — Automatic indexing on first start

## Description

**As** a developer who has just cloned the repo,
**I want** the gateway to automatically index the protected files on first start,
**so that** I do not have to run `kiri index` manually on every file before I can start working.

---

## Scenario

The developer clones the repo. The team already has a `.kiri/secrets` with three protected files.
They start the gateway:

```bash
docker compose up -d
```

The gateway starts, detects the existing `secrets` file, and automatically indexes the listed files:

```
[gateway] startup scan: 3 files in secrets
[gateway] indexed scorer.py         → 12 chunks, 21 symbols
[gateway] indexed calibrator.py     → 8 chunks, 5 symbols
[gateway] indexed feature_engine.py → 9 chunks, 5 symbols
[gateway] startup scan complete — ready
```

No manual intervention required. The gateway is protective from the very first request.

---

## Alternative scenario — CLI

If the developer prefers to index without starting the server:

```bash
kiri index --all
```

Output:

```
Indexing 3 protected files...
  ✓ scorer.py         12 chunks
  ✓ calibrator.py      8 chunks
  ✓ feature_engine.py  9 chunks
Done.
```

---

## Expected behaviour

- On startup, the Watcher performs an initial scan of all paths in `secrets`
- Files already indexed (same chunk count) are skipped — no unnecessary re-indexing
- Files not found are logged as warnings; they do not block startup
- `kiri index --all` does the same without starting the server

---

## Acceptance criteria

- [ ] On startup the kiri indexes all files present in `secrets` that are not yet in VectorStore
- [ ] Already-indexed files are not re-indexed (check on doc_id count)
- [ ] Missing files generate a warning in the log, not a crash
- [ ] `kiri index --all` works standalone without a running server
- [ ] After the initial scan the Watcher starts listening normally

---

## Notes

The current Watcher only reacts to file system events (future changes).
This US adds `Watcher.initial_scan()` — called once before `observer.start()`.
