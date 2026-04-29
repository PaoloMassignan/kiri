# Technology Stack — AI Gateway OnPrem

---

## Runtime & Linguaggio

### Python 3.11+
**Perché:** tutto l'ecosistema AI/ML (sentence-transformers, ChromaDB, Ollama client, FastAPI) è Python-first. Usare un altro linguaggio significherebbe wrappare librerie Python comunque. 3.11 per le performance migliorate e il typing più maturo.

---

## Deployment

### Docker + Docker Compose
**Perché:**
- Cross-platform senza configurare l'OS host — stesso `docker-compose.yml` su Windows, Mac, Linux
- `restart: always` sostituisce Windows Service / launchd / systemd con un unico meccanismo
- Isola tutte le dipendenze (Python, Ollama, ChromaDB, modelli) dentro l'immagine — il developer installa solo Docker Desktop
- Volume mount sulla directory del progetto: il container vede il codice sorgente e `.kiri/` senza copiare nulla

**Alternativa scartata:** Windows Service / systemd / launchd — richiedono configurazione diversa per ogni OS e privilegi di sistema.

---

## HTTP Proxy

### FastAPI + httpx
**Perché FastAPI:**
- Supporto nativo per streaming SSE (`StreamingResponse`) — necessario per Claude Code che usa `"stream": true`
- Async nativo — forwarding non bloccante, può gestire più richieste concorrenti
- Routing pulito per esporre più protocolli sullo stesso processo (`/v1/messages`, `/v1/chat/completions`, `/api/chat`)

**Perché httpx:**
- Client HTTP async — compatibile con FastAPI senza thread aggiuntivi
- Supporta streaming della risposta upstream in modo diretto

**Alternativa scartata:** aiohttp — più verboso, meno integrato con FastAPI.

---

## Embedding — L1 Similarity Gate

### sentence-transformers — `all-MiniLM-L6-v2`
**Perché:**
- Gira completamente offline dopo il download iniziale (~80MB)
- Vettori a 384 dimensioni — buon bilanciamento tra qualità semantica e velocità
- Ottimizzato per semantic similarity — esattamente il task del L1
- `pip install sentence-transformers` — zero server, zero processo aggiuntivo

**Perché questo modello specifico:**
- Benchmark interni mostrano qualità comparabile a modelli più grandi su task di similarity
- Latenza ~5ms per embedding su CPU — accettabile per uso runtime
- Già validato nel benchmark MVP (F1=0.976)

**Alternativa per codebase multilingua:** `paraphrase-multilingual-MiniLM-L12-v2` — stessa famiglia, supporto 50+ lingue. Configurabile in `config.yaml`.

---

## Vector Store — L1

### ChromaDB (embedded mode)
**Perché:**
- **Embedded** — nessun server separato, gira in-process dentro FastAPI come SQLite
- Persiste su disco in `.kiri/index/vectors.db` — sopravvive al restart del container
- API semplice: `add()`, `query()` — poche righe di codice
- Supporta cosine similarity nativa
- Già in stack nel gateway MVP

**Alternativa scartata:** Qdrant, Weaviate — richiedono un server separato, overkill per uso locale single-developer.

---

## Symbol Extraction + LLM Classifier — L2 e L3

### Ollama + qwen2.5:3b
**Perché Ollama:**
- Unico strumento che gestisce download, quantizzazione e serving dei modelli localmente
- API HTTP locale (`localhost:11434`) — chiamabile da Python senza SDK specifico
- Già in stack nel gateway MVP — zero nuove dipendenze
- Gira offline dopo il pull iniziale

**Perché qwen2.5:3b:**
- ~2GB quantizzato — scaricabile su hardware consumer
- Buone performance su task di estrazione strutturata (symbol extraction) e classificazione binaria (L3)
- Validato nel benchmark MVP su dataset manifattura

**Perché lo stesso modello per L2 e L3:**
- Un solo processo Ollama, un solo modello in memoria — nessun overhead aggiuntivo
- I task sono diversi ma entrambi leggeri: estrazione lista simboli (L2) e classificazione binaria (L3)

**Alternativa scartata:** Claude API per il classifier — richiederebbe rete, viola il principio on-prem. Tree-sitter per symbol extraction — deterministico ma cieco al contesto semantico, non cattura simboli in commenti o stringhe.

---

## File Watcher

### watchdog (Python)
**Perché:**
- Cross-platform — usa inotify su Linux, FSEvents su Mac, ReadDirectoryChangesW su Windows
- `pip install watchdog` — nessun processo aggiuntivo
- Monitora `.kiri/secrets` e triggera reindex automatico a ogni modifica

---

## CLI Interna

### Typer
**Perché:**
- Costruita su Click, genera automaticamente help, completion e validazione argomenti
- Interfaccia tipo git — subcomandi (`kiri add`, `kiri rm`) con un riga di codice
- Usata internamente dalla skill — il developer non la vede mai direttamente

---

## Configurazione

### YAML (`config.yaml`)
**Perché:**
- Human-readable — un developer può leggerlo e capirlo senza documentazione
- Committato nel repo — condiviso tra developer via git
- Supportato nativamente da `pyyaml`

**Struttura:**
```yaml
similarity_threshold: 0.75    # L1: sotto → PASS diretto
hard_block_threshold: 0.90    # L1: sopra → BLOCK diretto
action: block                 # block | sanitize
proxy_port: 8765
ollama_model: qwen2.5:3b
embedding_model: all-MiniLM-L6-v2
```

---

## Gestione Chiavi API

### Doppia chiave (kiri key + chiave reale)
**Perché:**
- Il developer riceve una chiave nominale `kr-xxx` generata dal container
- La chiave Anthropic reale `sk-ant-xxx` sta solo dentro il container
- Se il developer bypassa il proxy, la sua chiave non funziona con Anthropic → 401
- Chiavi nominali = audit trail per developer + revoca granulare

**Generazione:** `secrets` Python (`secrets.token_hex(32)`) al primo avvio del container, persistita in un file locale non committato.

---

## Skill Claude Code

### CLAUDE.md + hook
**Perché:**
- Claude Code legge `CLAUDE.md` nella root del progetto come contesto persistente
- Si può istruire Claude Code a riconoscere intent di protezione e chiamare la CLI interna
- Zero dipendenze aggiuntive — è configurazione, non codice

**Alternativa:** MCP (Model Context Protocol) server — più potente, permette tool use esplicito. Complessità maggiore, valutabile in fase 2.

---

## Riepilogo

| Componente | Tecnologia | Dimensione / Costo |
|---|---|---|
| Runtime | Python 3.11 | — |
| Deployment | Docker + Compose | ~500MB Docker Desktop |
| HTTP Proxy | FastAPI + httpx | pip |
| Embedding L1 | sentence-transformers | ~80MB |
| Vector Store | ChromaDB embedded | pip |
| Symbol extraction L2 | Ollama + qwen2.5:3b | ~2GB (una volta) |
| LLM Classifier L3 | Ollama (stesso processo) | incluso |
| File Watcher | watchdog | pip |
| CLI | Typer | pip |
| Config | YAML / pyyaml | pip |
| Skill | CLAUDE.md | zero |

**Dipendenze da installare sul sistema host:** solo Docker Desktop.
**Download una tantum:** modello Ollama qwen2.5:3b (~2GB) + modello embedding (~80MB).
**A runtime:** zero traffico di rete — tutto gira offline.
