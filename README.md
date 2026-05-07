# Kiri

**Use AI coding tools at full power — without sending your code to the cloud.**

Kiri is an on-premises proxy that sits between your AI coding tools and the cloud. It intercepts every outgoing LLM call and strips proprietary source code before it reaches the API — your implementation stays on your hardware, always. You keep the productivity; you give up nothing.

Works for a single developer or an entire team:

- **Single developer** — install the CLI, run `kiri serve` from your project directory, done. The quick start below covers this path end-to-end in under 15 minutes.
- **Team deployment** — run Kiri as a shared Docker service; each developer points their tools at the gateway and gets a personal `kr-` key. See [docs/guides/quickstart.md](docs/guides/quickstart.md) for the full team setup.

> Built with Claude for Claude. Kiri was developed using Claude Code — a deliberate choice: we used the tool we're protecting against to build the protection itself.

## Prerequisites

- Python 3.11+
- An API key for the LLM provider you use — Anthropic (`sk-ant-...`) or OpenAI (`sk-...`)

For the Docker deployment path: Docker Desktop (see [quickstart](docs/guides/quickstart.md)).

> **Note — Claude Code subscription (Max plan):** Kiri currently requires a standard
> Anthropic API key (`sk-ant-...`). The OAuth-based session token used by Claude Code
> Max subscriptions is not yet supported. Subscription support is on the roadmap.
> For now, a paid API account at [console.anthropic.com](https://console.anthropic.com) is required.

## Quick start

**1. Install**

**macOS / Linux**
```bash
git clone https://github.com/PaoloMassignan/kiri kiri
cd kiri
pip install --user pipx && python3 -m pipx ensurepath
```

**Windows (PowerShell)**
```powershell
git clone https://github.com/PaoloMassignan/kiri kiri
cd kiri
pip install --user pipx; python -m pipx ensurepath
```

Close and reopen your terminal, then:

**macOS / Linux**
```bash
pipx install --editable ./kiri
```

**Windows (PowerShell)**
```powershell
pipx install --editable .\kiri
```

Verify: `kiri --help`

**2. Create a project directory and protect a file** *(single terminal, no server needed)*

Open a new terminal — this is your **project directory**, separate from the `kiri/` repo you just cloned.

**macOS / Linux**
```bash
mkdir ~/my-project && cd ~/my-project
```

**Windows (PowerShell)**
```powershell
New-Item -ItemType Directory -Force "$HOME\my-project"; cd "$HOME\my-project"
```

Create a file with proprietary logic — save it as `pricing.py`:

```python
def calculate_final_price(quantity, is_premium):
    subtotal = 9.99 * quantity
    discount = subtotal * 0.0325
    tier = 2.47 if is_premium else 0.0
    return round(subtotal - discount + tier, 2)
```

```bash
# Protect and index it
kiri add pricing.py
kiri index pricing.py

# Verify the filter works — no server required
kiri inspect "explain calculate_final_price"
# Decision   : REDACT
# Reason     : symbol match: calculate_final_price
# Similarity : 0.0000
```

**3. Start the proxy** (blocking — open a second terminal for subsequent commands)

```bash
# In ~/my-project — store your real upstream key, then create a gateway key
mkdir -p .kiri
echo "sk-ant-YOUR-KEY" > .kiri/upstream.key   # macOS/Linux
# Windows: "sk-ant-YOUR-KEY" | Set-Content .kiri\upstream.key

kiri key create          # → kr-AbCdEfGhIjKlMnOpQrSt12
kiri serve               # leave this running
```

**4. Point your AI tool at the gateway** (in the second terminal)

```bash
# macOS / Linux
export ANTHROPIC_BASE_URL=http://localhost:8765
export ANTHROPIC_API_KEY=kr-AbCdEfGhIjKlMnOpQrSt12

# Windows (PowerShell)
$env:ANTHROPIC_BASE_URL = "http://localhost:8765"
$env:ANTHROPIC_API_KEY  = "kr-AbCdEfGhIjKlMnOpQrSt12"
```

For the full walkthrough — Docker deployment, key management, IDE integration — see **[docs/guides/quickstart.md](docs/guides/quickstart.md)**.

## Connect your AI coding tools

Point your tool at the gateway by changing one or two environment variables. The real key stays on your machine.

### Claude Code

```bash
export ANTHROPIC_BASE_URL=http://localhost:8765
export ANTHROPIC_API_KEY=kr-your-key-here
```

> **Requires an Anthropic API key** (`sk-ant-...`). Claude Code Max subscriptions
> (OAuth-based auth) are not yet supported — see note in Prerequisites above.

### Cursor / VS Code (.env)

```
ANTHROPIC_BASE_URL=http://localhost:8765
ANTHROPIC_API_KEY=kr-your-key-here
```

### OpenCode

Install OpenCode if you haven't already:

```bash
npm install -g opencode-ai
```

Create `opencode.json` in your **project root** (not inside the `kiri/` repo):

```json
{
  "model": "kiri/claude-sonnet-4-6",
  "provider": {
    "kiri": {
      "name": "Kiri Gateway",
      "npm": "@ai-sdk/anthropic",
      "options": {
        "baseURL": "http://localhost:8765",
        "apiKey": "kr-your-key-here"
      },
      "models": { "claude-sonnet-4-6": { "context": 200000 } }
    }
  }
}
```

Then run `opencode` from that directory. If `opencode` is not found after install, run `npx opencode@latest` instead.

### Codex CLI (OpenAI endpoint)

```bash
export OPENAI_BASE_URL=http://localhost:8765/v1
export OPENAI_API_KEY=kr-your-key-here
```

The gateway routes `/v1/messages` → Anthropic and `/v1/chat/completions` → OpenAI automatically. You only need the upstream key for the provider you use.

See **[§7 of the quickstart](docs/guides/quickstart.md#7-connect-your-ai-coding-tools)** for Cline, Continue.dev, and Windows PowerShell instructions.

## Audit log

After traffic flows through the gateway you can inspect what was filtered:

```bash
# Show the last 10 decisions
kiri log --tail 10

# Show only REDACT entries
kiri log --decision REDACT --since today

# Explain why the last request was filtered
kiri explain

# Show the full prompt as forwarded to the LLM (with stubs replacing protected code)
kiri explain --show-redacted
```

## How it works

Every outgoing LLM call passes through three filter levels:

| Level | Check | Action |
|-------|-------|--------|
| L1 | Vector similarity (ChromaDB cosine ≥ 0.90) | REDACT |
| L2 | Whole-word symbol match | REDACT |
| L3 | Ollama classifier (`qwen2.5:3b`), grace zone only | BLOCK if extraction intent, else REDACT |

`REDACT` strips protected function bodies and replaces them with a stub comment before forwarding — the developer still gets a useful response. `BLOCK` (HTTP 403) is reserved for when L3 detects explicit intent to extract IP.

## Repository layout

| Directory | Contents |
|-----------|----------|
| [`kiri/`](kiri/) | Production implementation — FastAPI proxy, filter pipeline, CLI, tests |
| [`kiri/tests/fixtures/`](kiri/tests/fixtures/) | Test corpus — synthetic codebases used by security and integration tests |
| [`docs/`](docs/) | All documentation: requirements (EARS), user stories, ADRs, SDD, diagrams |
| [`benchmarks/`](benchmarks/) | Evaluation datasets and benchmark runners |

For CLI reference, audit log, key management, and advanced configuration see [`kiri/CLAUDE.md`](kiri/CLAUDE.md).
