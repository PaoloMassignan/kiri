# US-03 — Remove protection from a file

## Description

**As** a developer,
**I want** to tell Claude Code "remove protection from this file",
**so that** the gateway stops blocking it in future requests.

---

## Interaction

> "remove protection from this file"
> "this file is no longer secret"
> "take risk_scorer.py out of the protected list"

Claude Code asks for confirmation before proceeding, then runs `kiri rm`.

**On-screen confirmation:**
```
⚠ You are removing protection from src/engine/risk_scorer.py
  From now on the content of this file may be sent to external LLMs.
  Confirm? (yes/no)

✓ Protection removed.
```

---

## Expected behaviour

- Claude Code always asks for explicit confirmation before removing protection
- Runs `kiri rm <file>` after confirmation
- The source file is not touched

---

## Acceptance criteria

- [ ] Requires explicit confirmation — protection cannot be removed by accident
- [ ] Works with natural language
- [ ] Confirmation message makes the impact clear (the file may leave the network)
- [ ] If the file is not protected, responds clearly without blocking errors
