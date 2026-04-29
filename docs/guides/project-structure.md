# Struttura del Progetto

## Repository root (`AI-Layer/`)

```
AI-Layer/   ← Kiri on-prem gateway
│
├── CLAUDE.md              ← contesto AI per il repo (entry point per Claude Code)
├── DECISIONS.md           ← decisioni chiave in una pagina (link agli ADR)
├── README.md              ← navigazione per umani
│
├── kiri/                ← implementazione del proxy (vedi sotto)
│
├── docs/
│   ├── requirements/      ← requisiti EARS (REQ-F, REQ-S, REQ-NF)
│   ├── adr/               ← Architecture Decision Records
│   ├── sdd/               ← Software Design Document (01–06)
│   ├── diagrams/          ← sequence e integration diagrams
│   ├── user-stories/      ← US-01 .. US-12
│   └── guides/            ← coding-rules, technology, project-structure
│
└── benchmarks/            ← dataset e runner per valutazione accuratezza
```

---

## Kiri (`kiri/`)

```
kiri/
│
├── CLAUDE.md              ← istruzioni gestione gateway (add/rm/status/inspect)
├── docker-compose.yml     ← avvio del container
├── Dockerfile
├── pyproject.toml
├── .env.example
│
├── src/
│   ├── main.py            ← entry point: avvia FastAPI + Watcher
│   │
│   ├── proxy/             ← HTTP proxy
│   │   ├── server.py      ← FastAPI app, auth, body-size limit, routing
│   │   ├── forwarder.py   ← httpx forwarding asincrono verso upstream
│   │   └── protocols/
│   │       ├── anthropic.py   ← /v1/messages
│   │       └── openai.py      ← /v1/chat/completions
│   │
│   ├── filter/            ← pipeline L1 → L2 → L3
│   │   ├── pipeline.py    ← orchestra i tre livelli, ritorna FilterResult
│   │   ├── l1_similarity.py   ← query ChromaDB cosine similarity
│   │   ├── l2_symbols.py      ← whole-word match su symbol store
│   │   └── l3_classifier.py   ← classificatore Ollama (grace zone only)
│   │
│   ├── indexer/           ← indicizzazione file protetti
│   │   ├── watcher.py         ← watchdog su .kiri/secrets → reindex auto
│   │   ├── chunker.py         ← divide file per funzione/classe
│   │   ├── embedder.py        ← sentence-transformers → float[]
│   │   └── symbol_extractor.py← Ollama → lista simboli
│   │
│   ├── store/             ← persistenza
│   │   ├── vector_store.py    ← ChromaDB embedded
│   │   ├── symbol_store.py    ← symbols.json
│   │   ├── secrets_store.py   ← .kiri/secrets (path + @symbol)
│   │   └── summary_store.py   ← cache summary per REDACT engine
│   │
│   ├── redaction/         ← motore REDACT
│   │   ├── engine.py          ← sostituisce corpi funzione con stub
│   │   └── summary_generator.py
│   │
│   ├── keys/
│   │   └── manager.py     ← kr- key: genera, valida, scadenza, revoca
│   │
│   ├── ratelimit/
│   │   └── limiter.py     ← sliding-window per chiave
│   │
│   ├── audit/
│   │   └── log.py         ← JSONL append-only, filter/tail/query
│   │
│   ├── auth/
│   │   └── admin_auth.py
│   │
│   ├── cli/               ← comandi gateway
│   │   ├── app.py         ← Typer root app
│   │   └── commands/
│   │       ├── add.py
│   │       ├── remove.py
│   │       ├── status.py
│   │       ├── inspect.py
│   │       └── index.py
│   │
│   └── config/
│       └── settings.py    ← Pydantic v2, legge config.yaml
│
├── tests/
│   ├── unit/              ← 32 file, ~520 test
│   ├── integration/       ← test HTTP end-to-end
│   └── security/          ← path traversal, scenari attacco
│
└── scripts/
    ├── install-hooks.sh   ← installa pre-commit hook (blocca kr- in commit)
    └── hooks/pre-commit
```

---

## Dipendenze tra moduli

```
main.py
  ├── proxy/server.py
  │     ├── protocols/*          ← normalizza input per protocollo
  │     ├── keys/manager.py      ← valida kr- key
  │     ├── ratelimit/limiter.py ← sliding window
  │     ├── filter/pipeline.py   ← PASS / BLOCK / REDACT
  │     ├── redaction/engine.py  ← se REDACT: oscura corpi funzione
  │     ├── audit/log.py         ← registra ogni decisione
  │     └── proxy/forwarder.py   ← forwarda con chiave upstream
  │
  └── indexer/watcher.py
        ├── store/secrets_store.py
        ├── indexer/chunker.py
        ├── indexer/embedder.py       → store/vector_store.py
        └── indexer/symbol_extractor.py → store/symbol_store.py

filter/pipeline.py
  ├── l1_similarity.py  → store/vector_store.py
  ├── l2_symbols.py     → store/symbol_store.py
  └── l3_classifier.py  ← Ollama HTTP (timeout → fail-open)
```

---

## File runtime (non committati)

```
kiri/.kiri/
  secrets          ← git ✅  policy di protezione
  config.yaml      ← git ✅  soglie, porte, modelli
  upstream.key     ← git ❌  chiave Anthropic reale (Docker secret)
  index/           ← git ❌  vettori + simboli (ricostruibile)
  keys/            ← git ❌  kr- keys per developer
  audit.log        ← git ❌  log JSONL append-only
```
