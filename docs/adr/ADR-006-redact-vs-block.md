# ADR-006: REDACT decision in the grace zone (0.75–0.90)

## Status
Accepted

## Context

In the grace zone (L1 similarity between 0.75 and 0.90), the gateway knows the prompt
is _close_ to protected code but not enough to be certain.

If L2 and L3 detect nothing suspicious, there are three options:

| Option | Behavior | FP Risk | FN Risk |
|---------|--------------|------------|------------|
| BLOCK | Block everything in the grace zone | High (frustrating) | Zero |
| PASS | Forward without changes | Zero | Medium |
| REDACT | Remove function bodies, forward the rest | Low | Low |

The typical grace zone case is: the developer mentions a function name or asks
to explain a concept that uses terms similar to those in the protected code,
without including the actual implementation.

## Decision

**REDACT in the grace zone when L2 and L3 pass:**

The gateway identifies the functions in the prompt that correspond to protected symbols
and replaces the body with a stub comment before forwarding:

```python
# Before (original prompt, grace zone):
def sliding_window_dedup(events: list[Event]) -> list[Event]:
    seen = set()
    result = []
    for e in events:
        key = (e.symbol, e.timestamp // WINDOW_SIZE)
        if key not in seen:
            seen.add(key)
            result.append(e)
    return result

# After (REDACT):
def sliding_window_dedup(events: list[Event]) -> list[Event]:
    # [implementation redacted — protected symbol]
    ...
```

The modified prompt reaches the LLM but without the implementation.
The LLM can answer questions about external behavior without seeing the code.

## Consequences

**Positive:**
- Developer can ask for help on how to _use_ a protected function
  without exposing the implementation
- Reduces false positives that would block legitimate workflows
- REDACT is recorded in the audit log with full details → complete visibility

**Negative:**
- Redaction is heuristic — if the implementation is in an unrecognizable form
  (lambda, generator expression), it may not be removed
- The LLM receives an artificially truncated prompt → potentially less useful response
- Additional complexity compared to a simple BLOCK/PASS

**Invariants:**
- REDACT occurs only in the grace zone (0.75 ≤ L1 < 0.90)
- REDACT occurs only if L2 and L3 found no match → if they find a match → BLOCK
- REDACT is always logged in the audit log

## Alternatives considered

**BLOCK everything in the grace zone:**
- Too many false positives on technical code (text with similar vocabulary)
- Developer would bypass the gateway to avoid the frustration

**PASS everything in the grace zone:**
- Potential code leakage on ambiguous but non-malicious requests
- Defeats the purpose of the grace zone itself

**Symbol anonymization (scramble):**
- Replaces `RiskScorer` → `ClassA` etc., restores in the response
- More transparent for the LLM, but requires a return mapping and
  can break the meaning of the response if renaming is incomplete
- Planned as a configurable alternative in a future version
