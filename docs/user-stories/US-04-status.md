# US-04 — View protected files

## Description

**As** a developer,
**I want** to ask Claude Code what is protected,
**so that** I always have a clear picture of what the gateway is monitoring.

---

## Interaction

> "what is protected?"
> "show me the secret files"
> "which files don't leave the network?"

**Response in chat:**
```
Protected files (3):
  • src/engine/risk_scorer.py      — 4 symbols (RiskScorer, sliding_window_dedup...)
  • src/billing/                   — 7 symbols
  • src/core/data_flow_engine.py   — 2 symbols

Gateway active on localhost:8765
```

---

## Acceptance criteria

- [ ] Works with natural language
- [ ] Shows protected paths and number of indexed symbols
- [ ] Confirms that the gateway is active
- [ ] If no files are protected, suggests how to get started
