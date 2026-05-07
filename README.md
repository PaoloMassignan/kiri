# Kiri

**Use AI coding tools at full power — without sending your code to the cloud.**

Kiri is an on-premises proxy that sits between your AI coding tools and the cloud. It intercepts every outgoing LLM call and strips proprietary source code before it reaches the API — your implementation stays on your hardware, always. You keep the productivity; you give up nothing.

Works for a single developer or an entire team:

- **Single developer** — run the one-line installer, done in under 10 minutes.
- **Team** — deploy Kiri as a shared Docker service; each developer gets a personal `kr-` key and connects with a single command. No changes to their existing tools.

> Built with Claude Code. Works with every AI coding tool. Kiri was developed using Claude Code — a deliberate choice: we used the tool we're protecting against to build the protection itself.

## Prerequisites

- Docker Desktop — [download](https://www.docker.com/products/docker-desktop/)
- An API key for the provider(s) you use:
  - Anthropic (`sk-ant-...`) from [console.anthropic.com](https://console.anthropic.com)
  - OpenAI (`sk-...`) from [platform.openai.com](https://platform.openai.com) — only if you use GPT models via Cursor or similar tools

## Installation

### macOS

```bash
git clone https://github.com/PaoloMassignan/kiri
cd kiri
./install/macos/install.sh
```

### Windows (PowerShell)

```powershell
git clone https://github.com/PaoloMassignan/kiri
cd kiri
.\install\windows\install.ps1
```

The installer asks for your API key and which tool you use (Claude Code, Cursor, or both), then handles everything: Docker stack, autostart at login, environment variables, and a `kiri` CLI wrapper.

### Linux

```bash
git clone https://github.com/PaoloMassignan/kiri
cd kiri
./install/linux/install.sh
```

Requires Docker Engine with the Compose plugin. If Docker requires `sudo` on your system, add your user to the `docker` group first:

```bash
sudo usermod -aG docker $USER   # then log out and back in
```

Autostart is configured via a systemd user service (`~/.config/systemd/user/kiri-gateway.service`). On systems without systemd, a startup command is added to your shell profile instead.

### Joining a team gateway

If your admin has already deployed a shared Kiri gateway:

```bash
./install/macos/connect.sh    # macOS
./install/linux/connect.sh    # Linux
.\install\windows\connect.ps1 # Windows
```

The script asks for the gateway URL and your personal `kr-` key, then sets the right environment variables. No Docker required.

### Uninstall

```bash
./install/macos/uninstall.sh           # macOS — keeps .kiri/ data
./install/macos/uninstall.sh --purge-data

./install/linux/uninstall.sh           # Linux — keeps .kiri/ data
./install/linux/uninstall.sh --purge-data

.\install\windows\uninstall.ps1        # Windows — keeps .kiri\ data
.\install\windows\uninstall.ps1 -PurgeData
```

---

## How it works

Every outgoing LLM call passes through three filter levels:

| Level | Check | Action |
|-------|-------|--------|
| L2 | Whole-word symbol match (always active) | REDACT |
| L1 | Vector similarity (ChromaDB cosine ≥ 0.90) | REDACT |
| L3 | Ollama classifier (`qwen2.5:3b`), grace zone 0.75–0.90 | BLOCK if extraction intent, else REDACT |

`REDACT` strips protected function bodies and replaces them with a stub comment before forwarding — the developer still gets a useful response. `BLOCK` (HTTP 403) is reserved for when L3 detects explicit intent to extract IP. L2 is always active regardless of L1/L3 availability.

## Connect your AI coding tools

Point your tool at the gateway with two environment variables. The real upstream key stays inside the Docker container and is never exposed.

**Claude Code**
```bash
export ANTHROPIC_BASE_URL=http://localhost:8765
export ANTHROPIC_API_KEY=kr-your-key-here
```

**Cursor / Windsurf / Cline / Continue.dev** — set base URL and API key in each tool's settings panel.

**OpenCode** — create `opencode.json` in your project root:
```json
{
  "model": "kiri/claude-sonnet-4-6",
  "provider": {
    "kiri": {
      "npm": "@ai-sdk/anthropic",
      "options": { "baseURL": "http://localhost:8765", "apiKey": "kr-your-key-here" },
      "models": { "claude-sonnet-4-6": { "context": 200000 } }
    }
  }
}
```

**Codex CLI / OpenAI-compatible tools**
```bash
export OPENAI_BASE_URL=http://localhost:8765/v1
export OPENAI_API_KEY=kr-your-key-here
```

The gateway routes `/v1/messages` → Anthropic and `/v1/chat/completions` → OpenAI automatically.

## Tool compatibility

| Tool | Status | Notes |
|------|--------|-------|
| Claude Code (API key) | ✅ Supported | |
| Cursor | ✅ Supported | |
| Windsurf | ✅ Supported | |
| Cline | ✅ Supported | |
| Continue.dev | ✅ Supported | |
| OpenCode | ✅ Supported | |
| Codex CLI | ✅ Supported | |
| Claude Pro / Max | ❌ Not supported | OAuth session tokens — roadmap |
| GitHub Copilot | ❌ Not supported | Hardcoded endpoint, cannot be redirected |
| AWS Bedrock | ❌ Not supported | IAM credentials, not API keys |
| Azure OpenAI | ⚠️ Untested | Configurable in principle, not validated |

The general rule: if the tool has a "base URL" setting and accepts a Bearer token, it works with Kiri.

## Audit log

```bash
kiri log --tail 10                        # last 10 decisions
kiri log --decision REDACT --since today  # today's redactions
kiri explain                              # why the last request was filtered
kiri explain --show-redacted              # full forwarded prompt with stubs
```

## Repository layout

| Directory | Contents |
|-----------|----------|
| [`kiri/`](kiri/) | Production implementation — FastAPI proxy, filter pipeline, CLI, tests |
| [`install/windows/`](install/windows/) | Windows installer (`install.ps1`, `connect.ps1`, `uninstall.ps1`, `disconnect.ps1`) |
| [`install/macos/`](install/macos/) | macOS installer (`install.sh`, `connect.sh`, `uninstall.sh`, `disconnect.sh`) |
| [`docs/`](docs/) | Requirements (EARS), user stories, ADRs, SDD, diagrams |
| [`benchmarks/`](benchmarks/) | Evaluation datasets and benchmark runners |

For CLI reference, key management, and advanced configuration see [`kiri/CLAUDE.md`](kiri/CLAUDE.md).
