# US-06 — Update the index automatically

## Description

**As** a developer,
**I want** the gateway to automatically update the index when I modify a protected file,
**so that** I don't have to think about it — protection always reflects the current code.

---

## Expected behaviour

- The gateway includes a **file watcher** that monitors the files in `.kiri/secrets`
- When a protected file is modified, reindexing starts automatically in the background
- The developer sees nothing — no notifications, no intervention required

---

## Acceptance criteria

- [ ] Reindexing starts within a few seconds of the file being modified
- [ ] It happens in the background — zero impact on the developer's work
- [ ] If Ollama is temporarily unavailable, reindexing is retried automatically
- [ ] Reindexing uses only local resources — no network traffic

---

## Notes

The file watcher runs as part of the gateway service — it is not a git hook and requires no per-project configuration. It is always active on all protected files.
