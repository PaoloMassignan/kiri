# US-02 — Protect a file

## Description

**As** a developer,
**I want** to tell Claude Code "make this file protected",
**so that** the kiri indexes the file and from that point on blocks its content in all future LLM calls.

---

## Interaction

The developer is in Claude Code and has opened `src/engine/risk_scorer.py`. They say in chat:

> "make this file protected"
> "add this file to secrets"
> "I don't want this file to leave the network"

Claude Code recognises the intent, asks for confirmation if necessary, and runs `kiri add` on the current file (or on the files mentioned).

**On-screen confirmation:**
```
✓ src/engine/risk_scorer.py added to protected files
  Detected symbols: RiskScorer, sliding_window_dedup, DataFlowEngine
  Also added as @symbol in secrets — they survive refactoring.
  From now on the content of this file will never leave the network.
```

---

## Expected behaviour

- Claude Code runs `kiri add <file>` on the current file or on those explicitly mentioned
- The kiri indexes the file on-prem (embedding + symbols via Ollama) — no network traffic
- The extracted symbols are written to `secrets` as `@symbol` as well as to the index
- L2 protection (symbols) is active immediately; L1 protection (semantic) after the next reindex
- The developer sees no commands and touches no terminals

---

## Acceptance criteria

- [ ] Works with natural language — no exact syntax required
- [ ] Claude Code correctly identifies the file to act on (open file, mentioned file, file in context)
- [ ] Clear confirmation with list of detected symbols
- [ ] Protection is active by the next response — no restart needed
- [ ] Idempotent: protecting an already-protected file warns without causing damage

---

## Notes

Analogous to running `git add` + `git commit` — it is an explicit, deliberate action by the developer. The Claude Code skill is the bridge between natural language and `kiri add`.
