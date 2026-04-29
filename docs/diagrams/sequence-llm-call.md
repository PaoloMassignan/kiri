# Sequence — LLM Call through the Gateway

---

## Case 1 — BLOCK (proprietary symbol detected)

```mermaid
sequenceDiagram
    actor Dev as Developer
    participant CC as Claude Code
    participant PX as HTTP Proxy<br/>(localhost:8765)
    participant FP as Filter Pipeline
    participant VS as Vector Store<br/>(ChromaDB)
    participant SS as Symbol Store
    participant OL as Ollama<br/>(L3 Classifier)
    participant EX as api.anthropic.com

    Dev->>CC: "refactor RiskScorer.sliding_window_dedup()"
    CC->>PX: POST /v1/messages {prompt}

    PX->>FP: filter(prompt)

    note over FP,VS: L1 — Similarity Gate
    FP->>VS: query(embed(prompt), top_k=5)
    VS-->>FP: [(risk_scorer.py, 0.91), ...]

    note over FP: score 0.91 ≥ hard_block_threshold 0.90

    note over FP,SS: L2 — Symbol Filter
    FP->>SS: scan(prompt)
    SS-->>FP: ["RiskScorer", "sliding_window_dedup"]

    note over FP: symbol found → BLOCK, L3 skipped

    FP-->>PX: BLOCK {reason: "RiskScorer", matched: "risk_scorer.py"}

    PX-->>CC: HTTP 400 {message: "Prompt contains protected IP"}
    CC-->>Dev: error with message
```

---

## Case 2 — PASS (generic prompt)

```mermaid
sequenceDiagram
    actor Dev as Developer
    participant CC as Claude Code
    participant PX as HTTP Proxy<br/>(localhost:8765)
    participant FP as Filter Pipeline
    participant VS as Vector Store<br/>(ChromaDB)
    participant SS as Symbol Store
    participant OL as Ollama<br/>(L3 Classifier)
    participant EX as api.anthropic.com

    Dev->>CC: "how do you implement a binary search in Python?"
    CC->>PX: POST /v1/messages {prompt}

    PX->>FP: filter(prompt)

    note over FP,VS: L1 — Similarity Gate
    FP->>VS: query(embed(prompt), top_k=5)
    VS-->>FP: [(risk_scorer.py, 0.12)] — below threshold

    note over FP: score 0.12 < similarity_threshold 0.75 → immediate PASS

    FP-->>PX: PASS

    PX->>EX: POST /v1/messages {prompt} — forwarding as-is
    EX-->>PX: LLM response
    PX-->>CC: LLM response
    CC-->>Dev: response
```

---

## Case 3 — Grace Zone → L3 Classifier decides

```mermaid
sequenceDiagram
    actor Dev as Developer
    participant CC as Claude Code
    participant PX as HTTP Proxy<br/>(localhost:8765)
    participant FP as Filter Pipeline
    participant VS as Vector Store<br/>(ChromaDB)
    participant SS as Symbol Store
    participant OL as Ollama<br/>(L3 Classifier)
    participant EX as api.anthropic.com

    Dev->>CC: "optimize this sliding window deduplication function"
    CC->>PX: POST /v1/messages {prompt}

    PX->>FP: filter(prompt)

    note over FP,VS: L1 — Similarity Gate
    FP->>VS: query(embed(prompt), top_k=5)
    VS-->>FP: [(risk_scorer.py, 0.81)]

    note over FP: 0.75 ≤ score 0.81 < 0.90 → grace zone, go to L2

    note over FP,SS: L2 — Symbol Filter
    FP->>SS: scan(prompt)
    SS-->>FP: [] — no exact symbol found

    note over FP,OL: L3 — LLM Classifier
    FP->>OL: classify(prompt, tags=["sliding_window", "dedup"])
    OL-->>FP: "extract_ip" (confidence: 0.87)

    note over FP: L3 → BLOCK

    FP-->>PX: BLOCK {reason: "L3 classifier", matched: "risk_scorer.py"}
    PX-->>CC: HTTP 400 {message: "Prompt contains protected IP"}
    CC-->>Dev: error with message
```

---

## Case 4 — SANITIZE (symbol found, sanitize mode)

```mermaid
sequenceDiagram
    actor Dev as Developer
    participant CC as Claude Code
    participant PX as HTTP Proxy<br/>(localhost:8765)
    participant FP as Filter Pipeline
    participant SN as Sanitizer
    participant VS as Vector Store<br/>(ChromaDB)
    participant SS as Symbol Store
    participant EX as api.anthropic.com

    Dev->>CC: "refactor RiskScorer.sliding_window_dedup()"
    CC->>PX: POST /v1/messages {prompt}

    PX->>FP: filter(prompt)

    FP->>VS: query(embed(prompt), top_k=5)
    VS-->>FP: [(risk_scorer.py, 0.91)]

    FP->>SS: scan(prompt)
    SS-->>FP: ["RiskScorer", "sliding_window_dedup"]

    FP-->>PX: SANITIZE {symbols: ["RiskScorer"→"ClassA", "sliding_window_dedup"→"method_0"]}

    PX->>SN: obscure(prompt, substitutions)
    SN-->>PX: "refactor ClassA.method_0()"

    PX->>EX: POST /v1/messages {"refactor ClassA.method_0()"}
    EX-->>PX: "you could rewrite ClassA.method_0() using..."

    PX->>SN: restore(response, substitutions)
    SN-->>PX: "you could rewrite RiskScorer.sliding_window_dedup() using..."

    PX-->>CC: restored response
    CC-->>Dev: response (real symbols, no IP leaked)
```

---

## Filter Pipeline decision summary

```
incoming prompt
      │
      ▼
  L1 similarity
      │
      ├── score < 0.75  ──────────────────────────────► PASS
      │
      ├── score ≥ 0.90  ──────────────────────────────► BLOCK (skip L2/L3)
      │
      └── 0.75 ≤ score < 0.90  (grace zone)
                │
                ▼
            L2 symbols
                │
                ├── symbol found  ─────────────────► BLOCK
                │
                └── no symbol
                          │
                          ▼
                      L3 Ollama
                          │
                          ├── "extract_ip"  ──────────► BLOCK
                          └── "benign"      ──────────► PASS
```
