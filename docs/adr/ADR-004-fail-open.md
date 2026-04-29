# ADR-004: Fail-open on internal L1 and L3 errors

## Status
Accepted

## Context

The gateway can encounter errors at two points on the critical path:

1. **L1 (ChromaDB):** the vector query fails (corrupted DB, lock, I/O error)
2. **L3 (Ollama):** the classifier does not respond within the timeout (Ollama not running,
   model not loaded, machine under load)

There are two choices:

| Strategy | L1/L3 error | Effect |
|-----------|-------------|---------|
| **Fail-open** | Treat as PASS → forward | Developer not blocked; potential temporary loss of protection |
| **Fail-closed** | Treat as BLOCK → block | Protection guaranteed; developer blocked until the problem is resolved |

## Decision

**Fail-open** on L1 and L3 errors.

Rationale:
- The gateway is a support tool, not a perimeter security firewall
- Blocking developer work for an internal infrastructure problem
  erodes trust in the product and leads to workarounds (disabling the gateway)
- L2 (symbol matching) is deterministic, does not depend on DB or LLM, and remains active
  even when L1/L3 fail → partial protection always guaranteed
- Errors are logged in the audit log with the reason — the team lead can see when
  the gateway operated in degraded mode

This decision is **explicit and documented** precisely because it is counterintuitive from
a security standpoint. An AI or a developer reading the code must not
"fix it" towards fail-closed.

## Consequences

**Positive:**
- Developer is never blocked by an infrastructure problem
- Gateway adoption more likely — does not interfere with daily work
- L2 (symbol match) is always active regardless of L1/L3

**Negative:**
- If ChromaDB corrupts silently, L1 is inactive without a visible alert
  → mitigation: error logging in audit log + warning at startup
- If Ollama is not running, L3 is always PASS in the grace zone
  → this is the expected behavior for those who have not installed Ollama (skip L3)

**Critical invariant:**
L2 (symbol matching, regex on dictionary) CANNOT fail silently —
it is a simple in-memory search on a Python dictionary. It is the safety net
that remains active even when L1 and L3 are degraded.

## Alternatives considered

**Fail-closed on L1:**
- A corrupted Docker volume or unexpected restart would make the gateway unusable
- The team would need to intervene before development could resume
- Unacceptable for a tool that must be transparent to the developer

**Fail-closed on L3:**
- Ollama is a separate process requiring ~2GB of RAM and warm-up time
- On machines with limited RAM, Ollama can be killed by the OS
- Blocking work every time Ollama is down would penalize DX without proportionate benefit

**Circuit breaker with manual fallback:**
- Complexity > benefit for v1
