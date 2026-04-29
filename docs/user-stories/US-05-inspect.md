# US-05 — Understand why a request was blocked

## Description

**As** a developer,
**I want** to understand why the gateway blocked my request,
**so that** I can rephrase it or find out which protected file triggered the block.

---

## Interaction

The developer sends a request to Claude Code and receives a block:

```
⛔ Request blocked by the gateway.
   Reason: protected content detected
   File: src/engine/risk_scorer.py
   Symbol found: RiskScorer

   You can rephrase the request without referencing this file,
   or ask me "why was it blocked?" to learn more.
```

If they ask for an explanation:

> "why was it blocked?"
> "what triggered the block?"

Claude Code shows the analysis detail (level L1/L2/L3, score, symbols).

---

## Expected behaviour

- The block message is always clear and non-technical
- The developer can ask for details in natural language
- Claude Code runs `kiri inspect` on the blocked prompt and displays the result in a readable form

---

## Acceptance criteria

- [ ] The block message indicates the file and/or symbol that triggered it
- [ ] The developer can ask for explanations without leaving Claude Code
- [ ] The detail shows which level (L1/L2/L3) made the decision
- [ ] No technical jargon in the default message — only what the developer needs to know

---

## Notes

`kiri inspect` is never explicit — it is always mediated by Claude Code as a response to a question.
