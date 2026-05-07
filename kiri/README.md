# Kiri

**A transparent proxy that prevents proprietary code and sensitive data from reaching external AI APIs — without changing how developers work.**

Point your AI tool at `localhost:8765` instead of `api.anthropic.com`. Everything else stays the same.

> Built with Claude Code. Works with every AI coding tool. This project was developed using Claude Code — a deliberate choice: we used the tool we're protecting against to build the protection itself.

---

## How it works

Every outgoing LLM call passes through three filter levels:

| Level | Method | Triggers at |
|-------|--------|-------------|
| L1 | Vector similarity (ChromaDB cosine) | ≥ 0.90 — hard block |
| L2 | Whole-word symbol matching (tree-sitter AST) | 0.75–0.90 grace zone |
| L3 | Local Ollama classifier (`qwen2.5:3b`) | 0.75–0.90 if L2 passes |

A blocked request returns HTTP 403. A `REDACT` decision replaces protected function
bodies with a stub comment before forwarding — the prompt reaches the model, but
without the implementation.

Nothing is sent to external services during filtering. The vector index, symbol store,
and classifier all run locally.

---

## Hello world

### 1. Install

```bash
git clone https://github.com/PaoloMassignan/kiri kiri
cd kiri/kiri
pip install -e .
```

### 2. Create a file worth protecting

```python
# pricing.py
_BASE_PRICE = 9.99
_DISCOUNT_RATE = 0.0325
_TIER_PREMIUM = 2.47

def calculate_final_price(quantity: int, is_premium: bool) -> float:
    base = _BASE_PRICE * quantity
    discount = base * _DISCOUNT_RATE
    tier = _TIER_PREMIUM if is_premium else 0.0
    return round(base - discount + tier, 2)
```

### 3. Protect and index it

```bash
cd ~/my-project
kiri add pricing.py
kiri index pricing.py
kiri status
```

```
=== Gateway Protection Status ===

Protected files (1):
  pricing.py

Indexed chunks : 2
Known symbols  : 4
```

### 4. Test the filter

Innocent query — passes:

```bash
kiri inspect "What is a good pricing strategy for SaaS products?"
```
```
Decision   : PASS
Reason     : similarity below threshold
Similarity : 0.1102
```

Code leak — blocked:

```bash
kiri inspect "def calculate_final_price(quantity, is_premium):
    base = 9.99 * quantity
    discount = base * 0.0325"
```
```
Decision   : BLOCK
Reason     : similarity above hard block threshold
Similarity : 0.9412
Symbols    : calculate_final_price
```

### 5. Run the proxy

```bash
# Store your real Anthropic key
echo "sk-ant-YOUR-KEY" > .kiri/upstream.key
chmod 600 .kiri/upstream.key

# Generate a kiri key for your tools
kiri key create
# → kr-AbCdEfGhIjKlMnOpQrSt12

# Start the proxy
kiri serve
# Gateway listening on http://127.0.0.1:8765
```

Point your tool at `http://127.0.0.1:8765` with the `kr-` key instead of your real API key.
A request containing your protected code returns HTTP 403. Everything else goes through normally.

### 6. Check what was blocked

```bash
kiri log --decision BLOCK --since today
```
```
2026-04-22T10:23:45Z  BLOCK   L1  similarity above hard block threshold  sim=0.941  [calculate_final_price]
```

---

## Installation options

### Local (single developer)

```bash
pip install -e .
kiri serve
```

Requires Python ≥ 3.11. Ollama is optional — the gateway degrades gracefully to L1+L2 only if L3 is unavailable.

### Docker (team deployment, includes Ollama L3 classifier)

```bash
echo "sk-ant-YOUR-KEY" > .kiri/upstream.key
docker compose up -d
docker compose exec gateway kiri key create
```

First run downloads `qwen2.5:3b` (~2 GB).

**Minimum hardware for the full stack:** 4 GB RAM, 3 GB disk, 2+ CPU cores.
GPU is optional — CPU inference takes ~1–2 s per prompt classification.
See [hardware and software requirements](docs/guides/quickstart.md#prerequisites) for details.

---

## What gets committed to git

```
.kiri/secrets      ✅  protected files and symbols
.kiri/config.yaml  ✅  thresholds and settings
.kiri/index/       ❌  rebuilt locally
.kiri/keys/        ❌  per-developer
.kiri/upstream.key ❌  your real API key — never commit this
```

---

## CLI reference

```bash
kiri add <path>          # protect a file
kiri add @SymbolName     # protect a symbol directly (no indexing needed)
kiri rm <path|@symbol>   # remove protection
kiri index <path>        # build embedding index immediately
kiri index --all         # index all protected files
kiri status              # show what is protected
kiri inspect "<prompt>"  # test a prompt against the filter
kiri inspect --file p.txt
kiri log --tail 50
kiri log --decision BLOCK --since today
kiri key create
kiri key list
kiri key revoke kr-...
kiri serve               # start the proxy
```

---

## Configuration

`.kiri/config.yaml` — committed to git, safe to share with your team:

```yaml
similarity_threshold: 0.75   # grace zone start (L2/L3 applied)
hard_block_threshold: 0.90   # L1 hard block
action: block                # "block" or "sanitize" (redact bodies)
proxy_port: 8765
ollama_model: qwen2.5:3b
symbol_min_length: 9
```

---

## Supported languages

Python, JavaScript, TypeScript, Java, Go, Rust, C, C++, C#

Symbol extraction and semantic chunking use tree-sitter AST parsing for all nine languages — not regex.

For a working Hello World example in each language, see
[docs/guides/quickstart.md](docs/guides/quickstart.md#hello-world--per-language).

---

## License

MIT — the gateway engine is free to use, modify, and distribute.
