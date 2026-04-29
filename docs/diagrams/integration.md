# Integration Diagram — AI Gateway OnPrem

```mermaid
graph TB
    subgraph HOST["🖥️ Developer Machine"]

        subgraph TOOLS["Tools"]
            CC["Claude Code\nCursor / Copilot\nANTHROPIC_BASE_URL=localhost:8765\nANTHROPIC_API_KEY=kr-xxx"]
            SKILL["Claude Code Skill\n'protect this file'"]
        end

        subgraph DOCKER["🐳 Docker Container  (restart: always)"]

            subgraph PROXY["HTTP Proxy — FastAPI :8765"]
                ANT["POST /v1/messages\nGET  /v1/models"]
                OAI["POST /v1/chat/completions"]
                OLL["POST /api/chat"]
            end

            subgraph KEYVAL["Key Validator"]
                KV["kr-xxx → authorized\nsk-ant-xxx → upstream"]
            end

            subgraph FILTER["Filter Pipeline"]
                L1["L1 — Similarity Gate\nCosine similarity\nvs indexed vectors"]
                L2["L2 — Symbol Filter\nText match on @symbol\nin secrets"]
                L3["L3 — LLM Classifier\nOllama — grace zone only"]
                L1 -->|"grace zone"| L2
                L2 -->|"no symbol"| L3
            end

            subgraph INDEXER["Indexer + File Watcher"]
                WATCH["File Watcher\nmonitors .kiri/secrets"]
                CHUNK["Chunker\nper function/class"]
                EMB["sentence-transformers\nall-MiniLM-L6-v2\n~80MB offline"]
                SYM["Symbol Extractor\nOllama qwen2.5:3b"]
                WATCH -->|"change detected"| CHUNK
                CHUNK --> EMB
                CHUNK --> SYM
            end

            OLLAMA["🦙 Ollama\nqwen2.5:3b"]

        end

        subgraph STORE[".kiri/  (Docker volume)"]
            subgraph GIT["← git ✅"]
                SEC["secrets\n─────────\nsrc/engine/risk_scorer.py\n@symbol RiskScorer\n@symbol sliding_window_dedup"]
                CFG["config.yaml\n─────────\nsimilarity_threshold: 0.75\nhard_block_threshold: 0.90\naction: block"]
            end
            subgraph LOCAL["← git ❌"]
                VDB["index/vectors.db\nChromaDB embedded\nfloat[] vectors"]
                SYMJ["index/symbols.json\n{path: [Symbol1, ...]}"]
                META["index/meta.json\n{path: {indexed_at, hash}}"]
            end
        end

        subgraph SRC["Project source  (Docker volume)"]
            CODE["src/\n  engine/risk_scorer.py\n  billing/\n  core/..."]
        end

    end

    subgraph CLOUD["☁️ Cloud"]
        ANTHAPI["api.anthropic.com\nsk-ant-xxx (real key)"]
    end

    %% Developer → tools
    DEV(["👤 Developer"])
    DEV -->|"natural language"| SKILL
    DEV -->|"LLM prompt"| CC

    %% Skill → internal CLI
    SKILL -->|"kiri add/rm/status"| WATCH

    %% Claude Code → Proxy
    CC -->|"POST /v1/messages\nkr-xxx"| ANT

    %% Proxy → Key Validator
    ANT --> KV
    OAI --> KV
    OLL --> KV

    %% Key Validator → Filter
    KV -->|"validates and passes"| L1

    %% Filter → store
    L1 <-->|"query top_k"| VDB
    L2 <-->|"scan symbols"| SYMJ
    L3 <-->|"classify"| OLLAMA

    %% Indexer → store
    EMB -->|"write vectors"| VDB
    SYM -->|"write symbols"| SYMJ
    SYM <-->|"uses"| OLLAMA
    CHUNK -->|"updates"| META

    %% Watcher → secrets
    WATCH <-->|"reads"| SEC

    %% Indexer → source
    CHUNK <-->|"reads files"| CODE

    %% Filter decision
    L1 -->|"BLOCK"| RESP_B["⛔ permission_error\nAnthropic-shaped"]
    L2 -->|"BLOCK"| RESP_B
    L3 -->|"BLOCK"| RESP_B
    L1 -->|"PASS"| FWD["Forwarding\nhttpx async"]
    L3 -->|"PASS"| FWD

    %% Forwarding → cloud
    FWD -->|"sk-ant-xxx"| ANTHAPI
    ANTHAPI -->|"response"| FWD
    FWD -->|"response"| CC

    %% Block → dev
    RESP_B -->|"readable error"| CC
    CC -->|"⛔ Blocked: RiskScorer\n(src/engine/risk_scorer.py)"| DEV

    %% Styles
    classDef cloud fill:#dbeafe,stroke:#3b82f6,color:#1e40af
    classDef docker fill:#f0fdf4,stroke:#22c55e,color:#14532d
    classDef store fill:#fefce8,stroke:#eab308,color:#713f12
    classDef block fill:#fef2f2,stroke:#ef4444,color:#991b1b
    classDef dev fill:#f5f3ff,stroke:#8b5cf6,color:#4c1d95

    class ANTHAPI cloud
    class PROXY,FILTER,INDEXER,OLLAMA,KEYVAL docker
    class STORE,GIT,LOCAL,SEC,CFG,VDB,SYMJ,META store
    class RESP_B block
    class DEV,SKILL,CC dev
```

---

## Legend

| Color | Area |
|---|---|
| 🟣 Purple | Developer and tools |
| 🟢 Green | Docker container (on-prem) |
| 🟡 Yellow | Disk store (`.kiri/`) |
| 🔵 Blue | Cloud (api.anthropic.com) |
| 🔴 Red | Block response |

---

## Main flows

| Flow | Path |
|---|---|
| **LLM Prompt** | Developer → Claude Code → Proxy → Key Validator → Filter Pipeline → PASS/BLOCK |
| **PASS** | Filter → Forwarding → api.anthropic.com → response → Developer |
| **BLOCK** | Filter → Anthropic-shaped permission_error → Claude Code → Developer |
| **File protection** | Developer (natural language) → Skill → Watcher → Indexer → Store |
| **Automatic reindex** | Watcher detects secrets change → Chunker → Embedder + Symbol Extractor → Store |
| **New dev** | git clone → secrets available → L2 active immediately → L1 reindex in background |
