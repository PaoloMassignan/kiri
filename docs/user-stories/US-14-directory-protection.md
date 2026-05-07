# US-14 — Protect a directory or glob pattern

## Description

**As** a developer,
**I want** to protect all files in a directory with a single command,
**so that** I don't have to add each file individually when an entire module is proprietary.

---

## Interaction

```bash
kiri add src/engine/           # all files in the directory, recursively
kiri add src/billing/
kiri add "src/**/*.pricing.*"  # glob pattern
```

Or in Claude Code:

> "protect everything under src/engine/"
> "the whole billing module is confidential"

---

## Expected behaviour

- `kiri add <dir>` adds all files in the directory recursively to `.kiri/secrets` as a single directory rule
- `kiri add <glob>` resolves the pattern and adds all matching files
- The directory rule is stored once in secrets — new files added to the directory later are automatically picked up by the watcher without running `kiri add` again
- Output: files added, files already protected (skipped), total symbols extracted

---

## Acceptance criteria

- [x] `kiri add src/engine/` protects all existing files in the directory at invocation time
- [x] A file added to `src/engine/` after the initial `kiri add` is automatically indexed without any manual step (watcher rescan every 60 s)
- [x] `kiri add "src/**/*.py"` adds all matching files resolved at invocation time
- [x] Already-protected files are skipped without error (idempotent)
- [x] `kiri status` shows the directory rule with file count (e.g. `@glob src/engine/  (8 file(s))`), not individual paths
- [x] `kiri rm src/engine/` removes the directory rule and purges all associated vectors and symbols

---

## Implementation notes

Rules are stored in `.kiri/secrets` as `@glob <pattern>` entries, separate from individual file paths (`_parse_path_entries` skips `@`-prefixed lines). This avoids ambiguity with the existing bare-path format and makes the secrets file self-documenting.

The watcher rescan thread (60 s interval) re-expands all active glob rules and diffs against the previously known set. New files are indexed, disappeared files are purged. Individual paths that also match a glob are not double-purged on glob removal.

**Status:** Done — `src/store/secrets_store.py`, `src/cli/commands/add.py`, `src/cli/commands/remove.py`, `src/cli/commands/status.py`, `src/indexer/watcher.py`.
