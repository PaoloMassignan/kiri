# ADR-008: REDACT as the default decision — BLOCK only on explicit malicious intent

## Status
Accepted — supersedes ADR-006 (partially)

## Context

ADR-006 introduced REDACT in the grace zone when both L2 and L3 pass.
However the pipeline continued to use BLOCK in three other cases:

| Case | Previous decision |
|------|---------------------|
| L1 ≥ 0.90 (hard block) | BLOCK |
| Grace zone + L2 match | BLOCK (or REDACT by strategy) |
| Grace zone + L3 "extract_ip" | BLOCK |

The problem: BLOCK and REDACT protect IP equivalently — both
prevent the implementation from reaching the LLM. But BLOCK breaks the developer's
workflow without any additional security benefit.

A developer who accidentally includes protected code in a prompt gains
nothing: neither a useful response nor an explanation of why. The practical effect
is that the gateway is perceived as an obstacle, increasing the likelihood
that it gets bypassed.

## Decision

**BLOCK is reserved for the only case where REDACT is insufficient:**
L3 detects deliberate intent to extract IP (`extract_ip`).

In all other cases where protected code is detected, the decision
is REDACT: the prompt is modified (function bodies replaced with stubs)
and forwarded. The developer gets a useful response; the IP is protected.

### New decision table

```
L2 match found                            → REDACT
L1 ≥ hard_block_threshold                 → REDACT (was BLOCK)
L1 < similarity_threshold                 → PASS
Grace zone + L3 "extract_ip"              → BLOCK  (only BLOCK remaining)
Grace zone + L3 "safe"                    → REDACT (was PASS or REDACT by strategy)
```

### Pipeline simplification

The routing for `ProtectionStrategy` (BLOCK vs REDACT per file) is removed
from the pipeline: it is no longer necessary to distinguish between "block-strategy" files and
"redact-strategy" files — the answer is always REDACT when there is a signal.

## Consequences

**Positive:**
- Significantly better developer experience: no wall when working
  with code close to the protected corpus
- Drastic reduction of the risk that the gateway gets bypassed out of frustration
- Simpler pipeline — one less code path, no per-file
  strategy logic
- REDACT is already logged in the audit log → no loss of visibility

**Negative:**
- L1 ≥ 0.90 (high certainty case) now gets REDACT instead of BLOCK.
  If the RedactionEngine fails to remove the code (e.g. inline implementation
  in a string), the IP might pass through. This fallback case is
  accepted as a trade-off against DX.
- BLOCK on explicit malicious intent (L3) remains as a deterrent; removing it
  would mean never signaling a deliberate extraction attempt.

## Alternatives considered

**Remove BLOCK on L3 "extract_ip" as well:**
- If the intent is explicitly malicious, forwarding + REDACT may not be
  sufficient (the prompt contains signals beyond function bodies)
- BLOCK in this case signals to the developer that the intent was detectable,
  which has deterrent and audit value

**Keep ProtectionStrategy per file:**
- Adds complexity without benefit: the BLOCK/REDACT choice per file
  was already debatable (REDACT protects equally well), and now becomes unnecessary
