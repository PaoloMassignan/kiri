# US-08 — Onboarding a new developer

## Description

**As** a new developer cloning the repo,
**I want** protection to be already active without any configuration,
**so that** I cannot accidentally send company IP to an external LLM from day one.

---

## Scenario

Dev B clones the repository for the first time. They do not know what is protected and have never used the gateway.

---

## Expected behaviour

```
git clone https://...repo...
cd progetto
docker compose up -d      ← starts the gateway (or starts automatically)
```

From this point on:

1. `.kiri/secrets` is already in the repo — it contains paths and `@symbol` entries
2. **L2 (symbols) is immediately active** — no DB needed, pure text matching
3. The Watcher detects that `index/` does not exist → starts re-indexing in the background
4. **L1 (semantics) becomes active** once re-indexing completes — a few minutes

During re-indexing, if Dev B tries to use a protected symbol:

```
⛔ Request blocked: protected symbol detected (RiskScorer)
   Reference file: src/engine/scorer.py
```

Semantic protection (L1) will kick in as soon as re-indexing is complete — in the background, without any intervention.

---

## Acceptance criteria

- [ ] Zero configuration required from the new developer
- [ ] L2 (symbols from `secrets`) active immediately after `docker compose up`
- [ ] L1 (similarity) active once automatic re-indexing completes
- [ ] The developer receives an informational message in Claude Code on first start:
      "Gateway active. X files and Y symbols protected in this project."
- [ ] Re-indexing runs in the background without blocking work

---

## Notes

The gap between clone and completed re-indexing is covered by the `@symbol` entries in `secrets`. There is no moment at which the new developer is entirely without protection.
