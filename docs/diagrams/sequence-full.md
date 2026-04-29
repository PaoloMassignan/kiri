# Sequence Diagram — All Actors

```mermaid
sequenceDiagram
    actor Dev as Developer
    participant CC as Claude Code
    participant GW as Gateway<br/>(HTTP Proxy)
    participant FP as Filter Pipeline
    participant VDB as Vector DB<br/>(ChromaDB)
    participant SDB as Symbol Store
    participant OL as Ollama<br/>(local LLM)
    participant LLM as api.anthropic.com<br/>(remote LLM)

    Dev->>CC: writes prompt

    CC->>GW: POST /v1/messages
    note over CC,GW: ANTHROPIC_BASE_URL=localhost:8765

    GW->>FP: filter(prompt)

    rect rgb(230, 240, 255)
        note over FP,VDB: L1 — Similarity Gate
        FP->>VDB: query(embed(prompt), top_k=5)
        VDB-->>FP: [(file, score), ...]
    end

    alt score < low threshold → immediate PASS
        FP-->>GW: PASS
        GW->>LLM: POST /v1/messages (as-is)
        LLM-->>GW: response
        GW-->>CC: response
        CC-->>Dev: response

    else score ≥ high threshold → immediate BLOCK
        FP-->>GW: BLOCK
        GW-->>CC: HTTP 400 "Protected IP detected"
        CC-->>Dev: error

    else grace zone → continue to L2
        rect rgb(255, 245, 220)
            note over FP,SDB: L2 — Symbol Filter
            FP->>SDB: scan(prompt)
            SDB-->>FP: [symbols found] or []
        end

        alt symbol found → BLOCK
            FP-->>GW: BLOCK {symbols}
            GW-->>CC: HTTP 400 "Protected IP detected"
            CC-->>Dev: error

        else no symbol → L3
            rect rgb(230, 255, 235)
                note over FP,OL: L3 — LLM Classifier (Ollama)
                FP->>OL: classify(prompt, matched_tags)
                OL-->>FP: "extract_ip" | "benign"
            end

            alt L3 → extract_ip
                FP-->>GW: BLOCK
                GW-->>CC: HTTP 400 "Protected IP detected"
                CC-->>Dev: error

            else L3 → benign → PASS
                FP-->>GW: PASS
                GW->>LLM: POST /v1/messages (as-is)
                LLM-->>GW: response
                GW-->>CC: response
                CC-->>Dev: response
            end
        end
    end
```

---

## Variant — SANITIZE mode

When `action: sanitize` is configured and symbols are found, instead of blocking the gateway obscures and restores them.

```mermaid
sequenceDiagram
    actor Dev as Developer
    participant CC as Claude Code
    participant GW as Gateway<br/>(HTTP Proxy)
    participant FP as Filter Pipeline
    participant VDB as Vector DB<br/>(ChromaDB)
    participant SDB as Symbol Store
    participant SN as Sanitizer
    participant LLM as api.anthropic.com<br/>(remote LLM)

    Dev->>CC: "refactor RiskScorer.sliding_window_dedup()"
    CC->>GW: POST /v1/messages {prompt}

    GW->>FP: filter(prompt)
    FP->>VDB: query(embed(prompt), top_k=5)
    VDB-->>FP: [(risk_scorer.py, 0.91)]
    FP->>SDB: scan(prompt)
    SDB-->>FP: ["RiskScorer", "sliding_window_dedup"]
    FP-->>GW: SANITIZE {map: {RiskScorer→ClassA, sliding_window_dedup→method_0}}

    GW->>SN: obscure(prompt, map)
    SN-->>GW: "refactor ClassA.method_0()"

    GW->>LLM: POST /v1/messages {"refactor ClassA.method_0()"}
    LLM-->>GW: "you could rewrite ClassA.method_0() using..."

    GW->>SN: restore(response, map)
    SN-->>GW: "you could rewrite RiskScorer.sliding_window_dedup() using..."

    GW-->>CC: response with real symbols
    CC-->>Dev: response (IP never left)
```

---

## Actors — responsibilities

| Actor | Type | Responsibility |
|---|---|---|
| Developer | human | writes prompt, receives response |
| Claude Code | external tool | HTTP client towards the gateway |
| Gateway (HTTP Proxy) | on-prem | intercepts, orchestrates, forwards |
| Filter Pipeline | on-prem | applies the 3 levels, returns decision |
| Vector DB (ChromaDB) | on-prem | similarity search on codebase embeddings |
| Symbol Store | on-prem | lookup of proprietary symbols in the prompt |
| Ollama (local LLM) | on-prem | L3 classifier — never sees source code |
| api.anthropic.com | cloud | remote LLM — receives only approved/obscured prompts |
| Sanitizer | on-prem | obscures symbols on output, restores in response |
