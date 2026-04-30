# US-13 — View and edit protection summaries

## Description

**As** a developer or admin,
**I want** to view and edit the summary that replaces a protected function's body
when sent to the LLM,
**so that** I can fix imprecise Ollama-generated descriptions and ensure the LLM
gets enough context to give useful responses without exposing implementation details.

---

## Context

When the gateway REDACTs a protected function, it replaces the body with an
Ollama-generated summary. That summary is what the LLM sees:

```python
def calculate_final_price(quantity, is_premium):
    # [PROTECTED] calculate_final_price
    # Purpose: Calculates the final price for a given quantity and premium status.
    # Parameters: quantity (numeric), is_premium (bool)
    # Returns: rounded float price
    ...
```

If Ollama produces a vague or inaccurate summary, the LLM cannot give useful
help. The developer needs to see and correct it.

---

## Interaction

```bash
# See what the LLM receives for a symbol
kiri summary show calculate_final_price

# [PROTECTED] calculate_final_price
# Purpose: Calculates the final price for a given quantity and premium status.
# Parameters: quantity (numeric), is_premium (bool)
# Returns: rounded float price
# Source: ollama  |  Updated: 2026-04-30T10:00:00Z

# List all protected symbols with their summaries
kiri summary list

# Symbol                   Source   Summary
# calculate_final_price    ollama   Calculates the final price for a given...
# _apply_discount          ollama   Applies a percentage discount to a price...
# RiskScorer               ollama   Computes a risk score using sliding window...

# Override with a manual summary
kiri summary set calculate_final_price \
  "Calculates the final sale price. Takes quantity and premium flag. Returns rounded float."

# Warning if the text contains numbers that may be implementation details
# ⚠  Warning: the summary contains numeric literals (e.g. 9.99, 0.0325).
#    These may reveal proprietary constants. Remove them if they are sensitive.

# Reset to Ollama-generated (removes the manual override)
kiri summary reset calculate_final_price

# Regenerate all summaries from Ollama
kiri summary reset --all
```

---

## Acceptance criteria

- [ ] `kiri summary list` displays all protected symbols with source (ollama/manual)
      and the first line of their summary
- [ ] `kiri summary list` shows "(no summaries)" when none exist
- [ ] `kiri summary show <symbol>` displays the full current summary plus
      source and updated timestamp
- [ ] `kiri summary show <symbol>` exits with error when the symbol is not found
- [ ] `kiri summary set <symbol> <text>` stores the text as a manual summary
      and marks it source=manual
- [ ] `kiri summary set` emits a warning when the text contains numeric literals
      that may be proprietary constants
- [ ] Manual summaries take priority over Ollama-generated ones in REDACT output
- [ ] `kiri summary reset <symbol>` removes a manual summary and falls back to
      the Ollama-generated one; if none exists, re-generates via Ollama
- [ ] `kiri summary reset --all` re-generates all summaries via Ollama
- [ ] All commands exit with code 1 and a clear message on error

---

## Notes

- The summary never contains the function body — only purpose, parameters,
  return value. The `set` command warns but does not block if the user includes
  numeric literals.
- If Ollama is unavailable during `reset`, the command exits with an error and
  the existing summary is preserved.
- `reset --all` is equivalent to `kiri index --all` in terms of summary
  regeneration; it can be slow if there are many protected files.
