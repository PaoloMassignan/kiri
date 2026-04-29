# US-07 — Protection after a refactoring

## Description

**As** a developer,
**I want** to be notified when a protected file is moved or split,
**so that** protection does not break silently after a refactoring.

---

## Scenario

The developer has protected `src/engine/risk_scorer.py`. They split it into two files:
- `src/engine/scorer.py`
- `src/engine/window_dedup.py`

The original file no longer exists.

---

## Interaction

The Watcher detects that a path in `secrets` no longer exists and notifies via Claude Code:

```
⚠️ Protected file not found: src/engine/risk_scorer.py
   It appears the file has been moved or split.

   Symbols still active via @symbol:
     • RiskScorer
     • sliding_window_dedup

   Do you want to update the protection with the new files?
```

The developer replies:

> "yes, protect scorer.py and window_dedup.py"

```
✓ src/engine/scorer.py added to protected files
✓ src/engine/window_dedup.py added to protected files
✓ src/engine/risk_scorer.py removed (no longer exists)
  Existing @symbols remain active.
```

---

## Expected behaviour

- The Watcher monitors the existence of paths declared in `secrets`
- If a path disappears, it notifies without blocking work
- `@symbol` entries declared in `secrets` remain active throughout the transition — protection continues even before the developer updates the paths
- The developer updates protection in natural language, without editing files

---

## Acceptance criteria

- [ ] The Watcher detects missing paths within a few seconds of the change
- [ ] The notification appears in Claude Code without interrupting work
- [ ] `@symbol` entries continue to block L2 even with stale paths
- [ ] After the update, the old path is removed from `secrets`
- [ ] Re-indexing of the new files starts automatically after confirmation

---

## Notes

`@symbol` entries are the safety net during the transition — they guarantee continuous protection even when the path is stale and the new files have not yet been indexed.
