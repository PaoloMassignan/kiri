# SDD-03: Filter Pipeline (L1/L2/L3)

## Overview

The filter pipeline is the heart of the gateway. It receives a text prompt and returns
a `FilterResult` with a decision, reason, level, maximum similarity, and matched symbols.

It is used by both the HTTP proxy (runtime) and `kiri inspect` (dry-run) —
same implementation, same results.

```python
@dataclass
class FilterResult:
    decision: str          # "PASS" | "BLOCK" | "REDACT"
    level: str             # "L1" | "L2" | "L3" | "PASS"
    reason: str            # textual description
    top_similarity: float  # 0.0–1.0
    matched_symbols: list[str]
```

---

## L1: Vector Similarity Gate

**Purpose:** detects semantic similarity between the prompt and indexed chunks.

**Implementation:**

1. The prompt is embedded with `sentence-transformers/all-MiniLM-L6-v2` (~5ms on CPU)
2. ChromaDB returns the top-5 chunks by cosine similarity
3. Decision based on the maximum score:

```python
MAX_SCORE = max(scores)

if MAX_SCORE >= hard_block_threshold:  # default 0.90
    return FilterResult(decision="BLOCK", level="L1", ...)

if MAX_SCORE < similarity_threshold:   # default 0.75
    return FilterResult(decision="PASS", level="PASS", ...)

# 0.75 ≤ MAX_SCORE < 0.90 → grace zone → continue to L2
```

**Fail-open:** if ChromaDB raises an exception, the result is PASS + error log.
See [ADR-004](../adr/ADR-004-fail-open.md).

---

## L2: Symbol Filter (grace zone)

**Purpose:** whole-word search for known symbols in the prompt text.

**Activated:** only in the grace zone (0.75 ≤ L1 < 0.90).

**Implementation:**

```python
for symbol in symbol_store.all_symbols():
    pattern = rf"\b{re.escape(symbol)}\b"
    if re.search(pattern, prompt):
        return FilterResult(decision="BLOCK", level="L2",
                            matched_symbols=[symbol], ...)
# no match → continue to L3
```

Symbols come from two sources:
- `@symbol` entries explicitly declared in `.kiri/secrets`
- symbols automatically extracted by Ollama during indexing of file paths

The whole-word match (`\b`) avoids false positives on substrings
(e.g. `Risk` does not match `RiskScorer`).

**Cannot fail silently:** it is an in-memory regex search on a Python dictionary.

---

## L3: LLM Classifier (grace zone, L2 pass)

**Purpose:** binary classifier that decides whether the prompt deliberately attempts
to extract protected IP.

**Activated:** only in the grace zone AND only if L2 found no symbols.

**Prompt template:**

```
You are a security classifier. A developer sent the following prompt to an AI assistant.
Protected intellectual property includes: {tags}.

Prompt: {prompt}

Does this prompt attempt to extract or expose protected intellectual property?
Answer with exactly one word: "extract_ip" or "safe".
```

**Implementation:**

```python
response = ollama.generate(model="qwen2.5:3b", prompt=formatted)
verdict = response["response"].strip().lower()

if "extract_ip" in verdict:
    # Only case where the pipeline returns BLOCK
    return FilterResult(decision="BLOCK", level="L3", ...)
else:
    return FilterResult(decision="REDACT", level="L3", ...)
```

**Fail-open:** if Ollama does not respond within the timeout, the result is PASS.
See [ADR-004](../adr/ADR-004-fail-open.md).

**Note on injection:** `str.format()` in Python does NOT re-process substituted values.
The user's `{prompt}` cannot expand placeholders in the template — safe by design.

---

## REDACT decision

REDACT is the default decision whenever protected code is detected,
except when explicit malicious intent is found (L3 `extract_ip` → BLOCK).

The `RedactionEngine` replaces the bodies of protected functions with stubs before
forwarding the prompt:

```python
# Input (prompt with protected code)
def sliding_window_dedup(events):
    seen = set()
    for e in events:
        # ... proprietary implementation
    return result

# Output (forwarded to upstream LLM)
def sliding_window_dedup(events):
    # [implementation redacted — protected symbol]
    ...
```

The developer gets a useful response; the proprietary implementation
never reaches the LLM. See [ADR-008](../adr/ADR-008-redact-as-default.md)
for the full rationale.

---

## Flow diagram

```
prompt
  │
  ▼
[symbol scan in prompt]  ← L2 always first
  │
  ├─ symbol found ──────────────► REDACT (L2)
  │
  └─ no symbol
       │
       ▼
  [embed prompt]
       │
       ▼
  [ChromaDB top-5 cosine]──error──► PASS (fail-open)
       │
       ├─ score ≥ 0.90 ──────────► REDACT (L1)
       │
       ├─ score < 0.75 ──────────► PASS   (L1)
       │
       └─ 0.75 ≤ score < 0.90
            │  (grace zone)
            ▼
       [Ollama classify]──timeout► PASS (fail-open)
            │
            ├─ "extract_ip" ──────► BLOCK  (L3) ← only BLOCK
            │
            └─ "safe" ────────────► REDACT (L3)
```

---

## Configuration

```yaml
# .kiri/config.yaml
similarity_threshold: 0.75    # lower bound of grace zone
hard_block_threshold: 0.90    # direct BLOCK threshold at L1
ollama_model: qwen2.5:3b
embedding_model: all-MiniLM-L6-v2
```

Thresholds can be lowered for more aggressive protection
or raised to reduce false positives on specific corpora.
