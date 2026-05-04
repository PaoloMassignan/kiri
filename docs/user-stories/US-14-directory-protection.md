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

- [ ] `kiri add src/engine/` protects all existing files in the directory at invocation time
- [ ] A file added to `src/engine/` after the initial `kiri add` is automatically indexed without any manual step
- [ ] `kiri add "src/**/*.py"` adds all matching files resolved at invocation time
- [ ] Already-protected files are skipped without error (idempotent)
- [ ] `kiri status` shows the directory rule (e.g. `src/engine/ [directory, 8 files]`), not individual paths
- [ ] `kiri rm src/engine/` removes the directory rule and purges all associated vectors and symbols

---

## Notes

Today `secrets_store.py:add_path` handles only single absolute file paths — there is no directory or glob resolution. This is the main usability gap for teams with proprietary modules: they should not need to enumerate every file.

Implementing directory rules also closes the re-index gap identified in US-06: the watcher can watch the directory itself, not just the secrets file, so new or modified files are picked up automatically.
