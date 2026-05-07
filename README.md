# Kiri

**Use AI coding tools at full power — without sending your code to the cloud.**

Kiri is an on-premises proxy that sits between your AI coding tools and the cloud. It intercepts every outgoing LLM call and strips proprietary source code before it reaches the API — your implementation stays on your hardware, always. You keep the productivity; you give up nothing.

Works for a single developer or an entire team:

- **Single developer** — install the CLI, run `kiri serve` from your project directory, done. The quick start below covers this path end-to-end in under 15 minutes.
- **Team deployment** — run Kiri as a shared Docker service; each developer points their tools at the gateway and gets a personal `kr-` key. See [docs/guides/quickstart.md](docs/guides/quickstart.md) for the full team setup.

> Built with Claude for Claude. Kiri was developed using Claude Code — a deliberate choice: we used the tool we're protecting against to build the protection itself.

## Prerequisites

- Docker Desktop — [download](https://www.docker.com/products/docker-desktop/)
- An API key for the provider(s) you use:
  - Anthropic (`sk-ant-...`) from [console.anthropic.com](https://console.anthropic.com)
  - OpenAI (`sk-...`) from [platform.openai.com](https://platform.openai.com) — only if you use GPT models via Cursor or similar tools


## Installation

Clone the repository, then run the one-line installer for your OS.
The installer handles Docker, keys, autostart, and tool configuration automatically.

### macOS

```bash
git clone https://github.com/PaoloMassignan/AI-Layer
cd AI-Layer
./install/macos/install.sh
```

### Windows (PowerShell)

```powershell
git clone https://github.com/PaoloMassignan/AI-Layer
cd AI-Layer
.\install\windows\install.ps1
```

The installer will ask for your Anthropic key, which tool you use (Claude Code, Cursor, or both), then set everything up — Docker stack, autostart, environment variables, and a `kiri` CLI wrapper.

### Joining a team gateway

If your admin has already deployed a shared Kiri gateway, you only need to configure your machine to point at it — no Docker required:

```bash
# macOS
./install/macos/connect.sh

# Windows
.\install\windows\connect.ps1
```

The script asks for the gateway URL and your personal `kr-` key (issued by your admin), then sets the right environment variables.

### To uninstall

```bash
# macOS
./install/macos/uninstall.sh           # keeps .kiri/ data
./install/macos/uninstall.sh --purge-data

# Windows
.\install\windows\uninstall.ps1        # keeps .kiri\ data
.\install\windows\uninstall.ps1 -PurgeData
```

---

## Quick start (manual / Linux)

If you prefer a manual setup or are on Linux:

```bash
pip install --user pipx && python3 -m pipx ensurepath
# reopen terminal, then:
pipx install --editable ./kiri
```

Store your upstream key and start the gateway:

```bash
mkdir -p .kiri
echo "sk-ant-YOUR-KEY" > .kiri/upstream.key
kiri key create    # → kr-AbCdEfGhIjKlMnOpQrSt12
kiri serve
```

Point your tool at the gateway:

```bash
export ANTHROPIC_BASE_URL=http://localhost:8765
export ANTHROPIC_API_KEY=kr-AbCdEfGhIjKlMnOpQrSt12
```

For the full walkthrough — Docker deployment, key management, IDE integration — see **[docs/guides/quickstart.md](docs/guides/quickstart.md)**.

## Connect your AI coding tools

Point your tool at the gateway by changing one or two environment variables. The real key stays on your machine.

### Claude Code

```bash
export ANTHROPIC_BASE_URL=http://localhost:8765
export ANTHROPIC_API_KEY=kr-your-key-here
```

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

## Tool compatibility

Kiri works with any tool that lets you set a custom base URL and accepts a standard API key. Tools with hardcoded endpoints or OAuth-based authentication cannot be redirected through the gateway.

| Tool | Status | Notes |
|------|--------|-------|
| Claude Code (API key) | ✅ Supported | Set `ANTHROPIC_BASE_URL` + `ANTHROPIC_API_KEY=kr-...` |
| Cursor | ✅ Supported | Set base URL and API key in Settings |
| Windsurf | ✅ Supported | Set base URL and API key in Settings |
| Cline | ✅ Supported | Configure provider URL in extension settings |
| Continue.dev | ✅ Supported | Configure provider URL in config.json |
| OpenCode | ✅ Supported | See configuration above |
| Codex CLI | ✅ Supported | Set `OPENAI_BASE_URL` |
| Claude Pro / Max | ❌ Not supported | Uses OAuth session tokens instead of API keys. Roadmap. |
| GitHub Copilot | ❌ Not supported | Endpoint is hardcoded — cannot be redirected to a custom gateway. |
| AWS Bedrock | ❌ Not supported | Uses IAM credentials, not API keys. |
| Azure OpenAI | ⚠️ Untested | Custom endpoints are configurable in principle but not validated. |

The general rule: if the tool has a "base URL" or "API endpoint" setting and accepts a Bearer token, it will work with Kiri.

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
| [`install/windows/`](install/windows/) | Windows installer (`install.ps1`, `connect.ps1`, `uninstall.ps1`, `disconnect.ps1`) |
| [`install/macos/`](install/macos/) | macOS installer (`install.sh`, `connect.sh`, `uninstall.sh`, `disconnect.sh`) |
| [`docs/`](docs/) | All documentation: requirements (EARS), user stories, ADRs, SDD, diagrams |
| [`benchmarks/`](benchmarks/) | Evaluation datasets and benchmark runners |

For CLI reference, audit log, key management, and advanced configuration see [`kiri/CLAUDE.md`](kiri/CLAUDE.md).
