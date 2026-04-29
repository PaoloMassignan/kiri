# ADR-001: Three-level filter pipeline (L1 + L2 + L3)

## Status
Accepted

## Context

The gateway must detect whether a prompt contains proprietary source code.
The problem has two asymmetric costs:

- **False negative** (code passes): IP leaves the network → irreversible damage
- **False positive** (code blocked): developer blocked → frustration, workarounds, eventual gateway deactivation

A single classifier cannot balance both:
- A precise LLM classifier has ~800ms latency on every request
- A single similarity threshold generates too many false positives on non-proprietary technical texts
- Symbol matching alone misses code that has not yet been indexed

From internal benchmarks on manufacturing datasets (creditscorer, billing, DSP):
- L1 alone (fixed threshold 0.75): too many FPs on similar technical documentation
- LLM alone: unacceptable as critical path (latency)
- L2 alone: blind to semantic content not yet indexed

## Decision

Sequential three-level pipeline with a **grace zone**:

| Phase | Condition | Action |
|------|-----------|--------|
| L1 cosine ≥ 0.90 | High certainty of semantic match | Immediate BLOCK (skip L2/L3) |
| L1 < 0.75 | No relevant similarity | Immediate PASS (skip L2/L3) |
| 0.75 ≤ L1 < 0.90 | Grace zone — ambiguous | Continue to L2 |
| L2 symbol match | Known symbol found in text | BLOCK |
| L2 no match | No symbol found | Continue to L3 |
| L3 classifier → "extract_ip" | LLM confirms risk | BLOCK or REDACT |
| L3 classifier → other | LLM rules out risk | PASS |

L3 is invoked only in the grace zone → in production on 5–15% of requests.

## Consequences

**Positive:**
- False positives minimized: the grace zone avoids BLOCK on generic technical texts
- L3 latency (Ollama ~200ms) paid infrequently
- L2 (regex) is deterministic and instantaneous — protects even before reindex
- L1 (vector query) is the main bottleneck: ~5ms on CPU

**Negative:**
- Hard-coded thresholds (0.75, 0.90) — must be calibrated on real corpus for each client
- Grace zone introduces a window where code can escape if neither L2 nor L3 detects it
- L3 requires local Ollama → additional infrastructure compared to pure ML

**Derived constraints:**
- L1 fail-open (ChromaDB error → PASS) — see ADR-004
- L3 fail-open (Ollama timeout → PASS) — see ADR-004

## Alternatives considered

**L1 only (similarity threshold):**
- Low threshold (0.5) → too many FPs on comments, technical documentation, similar naming
- High threshold (0.95) → too many FNs on slightly paraphrased code

**L3 only (LLM classifier):**
- ~800ms on every request → unacceptable as critical path
- Requires Ollama always active and responsive

**L1 + L3 without L2:**
- Symbol matching is O(n) on text, deterministic, zero latency
- Removing it means paying L3 on all cases that L2 resolves in microseconds

**Dynamic thresholds for L1:**
- Require feedback loop and historical data for each client
- Complexity >> current benefit
