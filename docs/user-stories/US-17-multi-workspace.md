# US-17 — Multi-workspace support

## Description

**As** a developer working on several projects simultaneously,
**I want** a single Kiri gateway instance to protect files from multiple workspaces,
**so that** I don't have to run one proxy per project and I can inspect a unified
audit log that spans all of them.

---

## Background

Today `kiri serve` watches a single workspace directory (the `workspace:` key in
config, defaulting to the directory from which the server was started). A developer
with three active repos must run three separate gateway processes on three separate
ports — each with its own index, its own audit log, and its own `.kiri/secrets` file.

Multi-workspace support lets a single gateway manage N workspaces declared in config.
Each workspace keeps its own secrets file and its own vector namespace, so symbol
collisions between projects are impossible. The gateway merges all namespaces when
filtering a request — protection is global across all declared workspaces.

---

## Interaction

```yaml
# .kiri/config.yaml
workspaces:
  - /home/alice/projects/helios
  - /home/alice/projects/billing
  - /home/alice/projects/auth-service
```

Or via CLI at runtime:

```bash
kiri workspace add /home/alice/projects/billing
kiri workspace rm  /home/alice/projects/billing
kiri workspace list
```

The `workspace:` (singular) key remains supported as a shorthand for a single entry.
A config with neither key defaults to the current working directory (existing behaviour).

---

## Expected behaviour

- On startup the gateway indexes all files listed in each workspace's `.kiri/secrets`
- Each workspace gets an isolated vector namespace (e.g. `ws_0`, `ws_1`) in ChromaDB
  so symbols with the same name in two projects do not collide
- The filter pipeline queries all namespaces in parallel and takes the union of results
  before applying the similarity threshold — the worst-case score across workspaces wins
- Each workspace's watcher thread runs independently; adding a file to one workspace
  does not trigger a rescan in another
- `kiri status` shows each workspace separately with its file count and chunk count
- `kiri log` includes a `workspace` field in each JSONL entry for correlation
- `kiri workspace add <path>` adds the workspace to the running config and begins
  indexing immediately without restarting the gateway
- `kiri workspace rm <path>` removes the workspace, purges its namespace, and stops
  its watcher thread

---

## Acceptance criteria

- [ ] gateway starts successfully with `workspaces:` list containing two or more paths
- [ ] `workspace:` (singular) and `workspaces:` (plural) are both accepted; using both
  in the same config file is an error reported at startup
- [ ] each workspace has an isolated ChromaDB namespace; symbols from workspace A are
  never returned when querying workspace B in isolation
- [ ] a prompt referencing a protected symbol in workspace B is BLOCKed/REDACTed even
  if that symbol is absent from workspace A's index
- [ ] `kiri status` lists each workspace with its path, file count, and chunk count
- [ ] `kiri log` entries include a `workspace` field containing the matched workspace
  path (or `"none"` if no workspace matched)
- [ ] `kiri workspace add <path>` hot-adds a workspace and begins indexing within 5 s
- [ ] `kiri workspace rm <path>` removes the workspace and purges its vectors within 5 s
- [ ] a path that does not exist is rejected at startup with a clear error message
- [ ] removing the last workspace does not crash the gateway; it logs a warning and
  continues serving (all requests will PASS — no protected files remain)

---

## Implementation notes

The `workspace` config key is kept for backwards compatibility. At load time
`settings.py` normalises both forms to `List[Path]`.

Each workspace gets its own `WatcherThread` instance (same class, different root).
The `IndexStore` abstraction gains a `namespace` parameter — ChromaDB collections are
named `kiri_<sha8(workspace_path)>` to remain stable across restarts regardless of
the declaration order in config.

The filter pipeline receives the full list of namespaces from `AppState` and runs
vector queries in parallel via `asyncio.gather`. The merged result set is ranked by
similarity score before threshold evaluation.

`kiri workspace add/rm` use the existing `kiri reload` mechanism to update the live
`AppState` without dropping in-flight requests.

**Status:** Planned

---

**User story covers:** single-developer multi-project workflow, team deployment where
one gateway serves several repos.
**Prerequisite:** REQ-F-012
