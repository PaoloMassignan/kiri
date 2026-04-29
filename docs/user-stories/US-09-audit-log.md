# US-09 — Audit log of blocked requests

## Description

**As** a security officer / team lead,
**I want** to see a persistent log of all requests that the gateway has blocked or allowed through,
**so that** I can verify that protection is working and understand who attempted what in the event of an incident.

---

## Scenario

The team lead wants to do a weekly review. They open Claude Code and ask:

> "show me the latest requests blocked by the gateway"

Claude Code responds with an excerpt from the log:

```
=== Latest blocked requests (5) ===

2026-04-16 14:23:11  BLOCK   L2 symbol match       probability_to_expected_loss
2026-04-16 13:58:02  BLOCK   L1 similarity 0.94    "show me how the scorer..."
2026-04-16 11:12:44  REDACT  L3 classifier         pricing_spread
2026-04-15 16:03:19  BLOCK   L2 symbol match       _compute_components
2026-04-15 09:41:55  PASS    —                     —
```

They can also filter:

> "show me only today's BLOCKs"

```bash
kiri log --decision block --since today
```

---

## Expected behaviour

- Every request is recorded in the log with: timestamp, decision, reason, filter level, symbols found, maximum similarity
- The prompt is not saved in full (privacy) — only the first 120 characters
- The log is append-only and is never truncated automatically
- `kiri log` displays the last N lines (default 50)
- The log survives container restarts (on a mounted volume)

---

## Acceptance criteria

- [ ] Every request (PASS, BLOCK, REDACT) generates a line in the log
- [ ] The log persists after a gateway restart
- [ ] `kiri log` shows the last 50 lines by default
- [ ] `kiri log --decision block` filters by decision
- [ ] `kiri log --tail N` shows the last N lines
- [ ] The prompt is truncated to 120 characters in the log
- [ ] The format is JSONL (one JSON entry per line) to facilitate external parsing

---

## Notes

The log is written by `server.py` after each pipeline decision.
The file lives at `.kiri/audit.log` — it must NOT be committed to git (add to `.gitignore`).
