# Quickstart — Kiri

This guide walks you through protecting a real file and verifying that Kiri
intercepts prompts containing your code. End-to-end in under 15 minutes.

There are two deployment modes:

| Mode | Who it's for | What you need |
|------|-------------|---------------|
| **Local** (§1–10) | Single developer, personal machine | Python 3.11+, no Docker |
| **Docker** (§ Production setup) | Team deployment, shared environment | Docker Desktop + Ollama |

The guide follows the **local** path first — no Docker required. Skip to
[Production setup](#production-setup-docker--ollama) when you are ready to
deploy for a team.

---

## Prerequisites

### Software

| Software | Version | Install |
|----------|---------|---------|
| Python | ≥ 3.11 | [python.org](https://www.python.org/downloads/) or `brew install python@3.11` |
| pip | bundled with Python | — |
| git | any | [git-scm.com](https://git-scm.com/) or `brew install git` |
| curl | any | pre-installed on macOS/Linux; on Windows install [curl for Windows](https://curl.se/windows/) or use Git Bash |

> **Why Python?** The gateway proxy is written in Python — it runs as a local background
> process that intercepts LLM calls. Your own project (C#, TypeScript, Go, Java…) is
> unaffected: you only need Python to install and run the gateway itself.

For the **Docker path only** (§ Production setup):

| Software | Version | Install |
|----------|---------|---------|
| Docker Desktop | ≥ 4.x | [docs.docker.com/get-docker](https://docs.docker.com/get-docker/) — includes Compose |

### Hardware

**Local path** (Python only, no Ollama):

| Resource | Minimum |
|----------|---------|
| RAM | 2 GB free |
| Disk | 1 GB (Python deps + embedding model `all-MiniLM-L6-v2` ≈ 90 MB) |
| CPU | Any |

**Docker path** (gateway + Ollama L3 classifier):

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 6 GB free | 8 GB |
| Disk | 5 GB free | 10 GB (model cache survives container restarts) |
| CPU | 4 cores | 8 cores (Ollama inference is CPU-bound without a GPU) |
| GPU | not required | NVIDIA GPU with ≥ 4 GB VRAM cuts L3 latency from ~4 s to < 1 s |

> The Ollama model `qwen2.5:3b` is ~2 GB on disk. It is downloaded automatically
> on the first `docker compose up`.

### Accounts

| Account | Where | Why |
|---------|-------|-----|
| Anthropic API key (`sk-ant-...`) | [console.anthropic.com](https://console.anthropic.com) | Required for live-proxy steps (§5–6) if using Claude models |
| OpenAI API key (`sk-...`) | [platform.openai.com](https://platform.openai.com) | Alternative — use if your tools target GPT models |

You only need one of the two keys. The gateway routes traffic automatically based on
the endpoint path (`/v1/messages` → Anthropic, `/v1/chat/completions` → OpenAI).

---

## 0. Clone the repository

If you haven't already:

**macOS / Linux**
```bash
git clone https://github.com/PaoloMassignan/kiri kiri
cd kiri
```

**Windows (PowerShell)**
```powershell
git clone https://github.com/PaoloMassignan/kiri kiri
cd kiri
```

All install commands in §1 are run from this directory (the **repo root**).

---

## 1. Install

Use **pipx** to install the `kiri` CLI into an isolated environment and add it
to your PATH automatically. You only do this once — `kiri` will be available
in every new terminal without activating a virtual environment.

**macOS / Linux**

```bash
pip install --user pipx
python3 -m pipx ensurepath
```

Close and reopen your terminal, then:

```bash
pipx install --editable ./kiri
```

**Windows (PowerShell)**

```powershell
pip install --user pipx
python -m pipx ensurepath
```

Close and reopen PowerShell, then:

```powershell
pipx install --editable .\kiri
```

Verify the installation:

```bash
kiri --help
```

You should see the Kiri command list.

> **Troubleshooting — `kiri: command not found`**
>
> - **pipx path:** `ensurepath` adds the pipx bin directory to your PATH, but the
>   change only takes effect in a **new terminal**. Close the current one and open
>   a fresh window, then retry.
> - **venv path:** you must activate the venv in **every new terminal** before
>   `kiri` is available:
>   - macOS/Linux: `source kiri/.venv/bin/activate`
>   - Windows: `kiri\.venv\Scripts\Activate.ps1`
> - **Still stuck (Windows)?** Run `python -m pipx ensurepath` and check that
>   `%USERPROFILE%\AppData\Local\Programs\Python\<ver>\Scripts` is in your
>   `$PATH` (System Properties → Environment Variables).

> **Alternative — venv (no pipx):**
>
> **macOS / Linux**
> ```bash
> cd kiri          # enter the Python package folder inside the repo
> python3 -m venv .venv
> source .venv/bin/activate
> pip install -e .
> ```
>
> **Windows (PowerShell)**
> ```powershell
> cd kiri          # enter the Python package folder inside the repo
> python -m venv .venv
> .venv\Scripts\Activate.ps1
> pip install -e .
> ```
>
> With a venv you must run `.venv\Scripts\Activate.ps1` (Windows) or
> `source .venv/bin/activate` (macOS/Linux) every time you open a new terminal
> before using `kiri`.

---

## 2. Set up a project directory

The gateway is always run **from the root of the project you want to protect**.
Its state lives in `.kiri/` inside that directory.

Open a **new terminal** (you no longer need the repo terminal — this new one is
where you'll spend the rest of the guide) and create your project:

**macOS / Linux**

```bash
mkdir ~/my-project
cd ~/my-project
```

**Windows (PowerShell)**

```powershell
New-Item -ItemType Directory -Force "$HOME\my-project"
cd "$HOME\my-project"
```

> **venv users:** activate the venv in this new terminal before running any
> `kiri` command. The activation path is relative to where you cloned the repo,
> not to `~/my-project`:
>
> macOS/Linux: `source ~/path/to/kiri/.venv/bin/activate`
> Windows: `~/path/to/kiri/.venv\Scripts\Activate.ps1`
>
> You will need to do this in every new terminal you open for the rest of the guide.

Create the file you want to protect — a pricing engine with proprietary constants.

**Python** — save as `pricing.py`:

```python
_BASE_PRICE = 9.99
_DISCOUNT_RATE = 0.0325
_TIER_PREMIUM = 2.47

def calculate_final_price(quantity: int, is_premium: bool) -> float:
    base = _BASE_PRICE * quantity
    discount = base * _DISCOUNT_RATE
    tier = _TIER_PREMIUM if is_premium else 0.0
    return round(base - discount + tier, 2)
```

**C#** — save as `Pricing.cs`:

```csharp
namespace MyApp.Billing;

internal static class PricingEngine
{
    private const decimal BasePrice     = 9.99m;
    private const decimal DiscountRate  = 0.0325m;
    private const decimal TierPremium   = 2.47m;

    public static decimal CalculateFinalPrice(int quantity, bool isPremium)
    {
        var subtotal = BasePrice * quantity;
        var discount = subtotal * DiscountRate;
        var tier     = isPremium ? TierPremium : 0m;
        return Math.Round(subtotal - discount + tier, 2);
    }
}
```

**TypeScript** — save as `pricing.ts`:

```typescript
const BASE_PRICE    = 9.99;
const DISCOUNT_RATE = 0.0325;
const TIER_PREMIUM  = 2.47;

export function calculateFinalPrice(quantity: number, isPremium: boolean): number {
  const base     = BASE_PRICE * quantity;
  const discount = base * DISCOUNT_RATE;
  const tier     = isPremium ? TIER_PREMIUM : 0;
  return Math.round((base - discount + tier) * 100) / 100;
}
```

**Go** — save as `pricing.go`:

```go
package billing

const (
    basePrice    = 9.99
    discountRate = 0.0325
    tierPremium  = 2.47
)

func CalculateFinalPrice(quantity int, isPremium bool) float64 {
    base     := basePrice * float64(quantity)
    discount := base * discountRate
    tier     := 0.0
    if isPremium {
        tier = tierPremium
    }
    return math.Round((base-discount+tier)*100) / 100
}
```

**Java** — save as `PricingEngine.java`:

```java
package com.myapp.billing;

public final class PricingEngine {
    private static final double BASE_PRICE    = 9.99;
    private static final double DISCOUNT_RATE = 0.0325;
    private static final double TIER_PREMIUM  = 2.47;

    public static double calculateFinalPrice(int quantity, boolean isPremium) {
        double base     = BASE_PRICE * quantity;
        double discount = base * DISCOUNT_RATE;
        double tier     = isPremium ? TIER_PREMIUM : 0.0;
        return Math.round((base - discount + tier) * 100.0) / 100.0;
    }
}
```

**Rust** — save as `pricing.rs`:

```rust
const BASE_PRICE:    f64 = 9.99;
const DISCOUNT_RATE: f64 = 0.0325;
const TIER_PREMIUM:  f64 = 2.47;

pub fn calculate_final_price(quantity: u32, is_premium: bool) -> f64 {
    let subtotal = BASE_PRICE * quantity as f64;
    let discount = subtotal * DISCOUNT_RATE;
    let tier     = if is_premium { TIER_PREMIUM } else { 0.0 };
    (subtotal - discount + tier) * 100.0_f64.round() / 100.0
}
```

**C++** — save as `pricing.hpp`:

```cpp
#pragma once
namespace billing {

constexpr double kBasePrice    = 9.99;
constexpr double kDiscountRate = 0.0325;
constexpr double kTierPremium  = 2.47;

double CalculateFinalPrice(int quantity, bool is_premium) {
    double subtotal = kBasePrice * quantity;
    double discount = subtotal * kDiscountRate;
    double tier     = is_premium ? kTierPremium : 0.0;
    return std::round((subtotal - discount + tier) * 100.0) / 100.0;
}

} // namespace billing
```

> **Language support:** Python, C#, TypeScript, Go, Java, Rust, and C++ are all
> supported out of the box — tree-sitter parses the file and registers function
> names and constants in the symbol index automatically.

---

## 3. Protect the file

Run all commands from your **project directory** (`~/my-project`).

```bash
# use the filename you created above
kiri add pricing.py
```

Expected output:

```
Added pricing.py to protected files (run 'kiri index' to index now if server is not running)
```

Build the embedding index immediately (the server does this automatically via the
file watcher when it is running, but we haven't started it yet):

```bash
kiri index pricing.py
```

> The first run downloads the embedding model (~90 MB). This can take a minute.
> Subsequent calls are instant.

Expected output:

```
Indexed pricing.py
```

Verify:

```bash
kiri status
```

Expected output:

```
=== Gateway Protection Status ===

Protected files (1):
  /absolute/path/to/my-project/pricing.py

Explicit symbols (0):
  (none)

Indexed chunks : 1
Known symbols  : 4
```

> **What just happened?** The file was parsed with tree-sitter, split into semantic
> chunks, embedded into a local ChromaDB vector store, and its symbols
> (`calculate_final_price`, `9.99`, `0.0325`, `2.47`) were registered in the
> symbol index. Nothing left the machine.

---

## 4. Test the filter — `kiri inspect`

`inspect` runs the full filter pipeline locally, without starting the proxy server.
It's the fastest way to verify your protection is working.

### Innocent query — should PASS

```bash
kiri inspect "What is a good pricing strategy for SaaS products?"
```

Expected output:

```
Decision   : PASS
Reason     : below threshold (score=0.6xx)
Similarity : 0.6xxx
```

### Code leakage — should REDACT

Use the snippet matching the language you chose in §2:

**Python**

```bash
kiri inspect "Here is our pricing logic:

def calculate_final_price(quantity, is_premium):
    subtotal = 9.99 * quantity
    discount = subtotal * 0.0325
    tier = 2.47 if is_premium else 0.0
    return round(subtotal - discount + tier, 2)"
```

**C#**

```bash
kiri inspect "Here is our pricing logic:

public static decimal CalculateFinalPrice(int quantity, bool isPremium)
{
    var subtotal = 9.99m * quantity;
    var discount = subtotal * 0.0325m;
    var tier     = isPremium ? 2.47m : 0m;
    return Math.Round(subtotal - discount + tier, 2);
}"
```

**TypeScript**

```bash
kiri inspect "Here is our pricing logic:

export function calculateFinalPrice(quantity: number, isPremium: boolean): number {
  const subtotal = 9.99 * quantity;
  const discount = subtotal * 0.0325;
  const tier     = isPremium ? 2.47 : 0;
  return Math.round((subtotal - discount + tier) * 100) / 100;
}"
```

**Go**

```bash
kiri inspect "Here is our pricing logic:

func CalculateFinalPrice(quantity int, isPremium bool) float64 {
    subtotal := 9.99 * float64(quantity)
    discount := subtotal * 0.0325
    tier := 0.0
    if isPremium { tier = 2.47 }
    return math.Round((subtotal-discount+tier)*100) / 100
}"
```

**Java**

```bash
kiri inspect "Here is our pricing logic:

public static double calculateFinalPrice(int quantity, boolean isPremium) {
    double subtotal = 9.99 * quantity;
    double discount = subtotal * 0.0325;
    double tier     = isPremium ? 2.47 : 0.0;
    return Math.round((subtotal - discount + tier) * 100.0) / 100.0;
}"
```

**Rust**

```bash
kiri inspect "Here is our pricing logic:

pub fn calculate_final_price(quantity: u32, is_premium: bool) -> f64 {
    let subtotal = 9.99 * quantity as f64;
    let discount = subtotal * 0.0325;
    let tier     = if is_premium { 2.47 } else { 0.0 };
    (subtotal - discount + tier) * 100.0_f64.round() / 100.0
}"
```

**C++**

```bash
kiri inspect "Here is our pricing logic:

double CalculateFinalPrice(int quantity, bool is_premium) {
    double subtotal = 9.99 * quantity;
    double discount = subtotal * 0.0325;
    double tier     = is_premium ? 2.47 : 0.0;
    return std::round((subtotal - discount + tier) * 100.0) / 100.0;
}"
```

Expected output for all languages (exact symbol names vary by language):

```
Decision   : REDACT
Reason     : symbol match: calculate_final_price, 9.99, 0.0325, 2.47
Similarity : 0.0000
Symbols    : calculate_final_price, 9.99, 0.0325, 2.47
```

> **REDACT vs BLOCK:**
> - **REDACT** — L2 (whole-word symbol match) caught the function name and the
>   proprietary numeric constants. The implementation will be stripped and replaced
>   with a stub comment before the prompt is forwarded. The LLM still gets a useful
>   response, but without the protected code.
> - **BLOCK (HTTP 403)** — only issued when the L3 Ollama classifier detects explicit
>   intent to extract IP. L3 requires Docker + Ollama — see
>   [Production setup](#production-setup-docker--ollama). In local mode, the
>   strongest outcome is always REDACT.

### Partial leakage — proprietary constants

Even a snippet without the function name is caught because the numeric constants
are indexed as symbols:

```bash
kiri inspect "subtotal = 9.99 * quantity; discount = subtotal * 0.0325"
```

Expected output:

```
Decision   : REDACT
Reason     : symbol match: 9.99, 0.0325
Similarity : 0.0000
Symbols    : 9.99, 0.0325
```

---

## 5. Run the proxy server

The gateway acts as a transparent proxy: your tools talk to `localhost:8765` instead
of the upstream API. The real key stays on your machine and is never exposed to
developers.

| Your request path | Routed to | Key file |
|-------------------|-----------|----------|
| `/v1/messages` | Anthropic (`api.anthropic.com`) | `.kiri/upstream.key` |
| `/v1/chat/completions` | OpenAI (`api.openai.com`) | `.kiri/openai.key` |

You only need to store the key for the provider you actually use.

### Step A — Store the upstream key

Run from your **project directory** (`~/my-project`):

**macOS / Linux**

```bash
mkdir -p .kiri

# Anthropic (Claude models):
echo "sk-ant-YOUR-REAL-KEY" > .kiri/upstream.key
chmod 600 .kiri/upstream.key

# OpenAI (GPT models) — skip if using Anthropic:
# echo "sk-YOUR-OPENAI-KEY" > .kiri/openai.key
# chmod 600 .kiri/openai.key
```

**Windows (PowerShell)**

```powershell
New-Item -ItemType Directory -Force .kiri

# Anthropic (Claude models):
"sk-ant-YOUR-REAL-KEY" | Set-Content .kiri\upstream.key
icacls .kiri\upstream.key /inheritance:r /grant:r "$($env:USERNAME):(R)"

# OpenAI (GPT models) — skip if using Anthropic:
# "sk-YOUR-OPENAI-KEY" | Set-Content .kiri\openai.key
```

Alternatively, use environment variables (the file takes precedence if both exist):

**macOS / Linux**
```bash
export ANTHROPIC_API_KEY=sk-ant-YOUR-REAL-KEY
```

**Windows (PowerShell)**
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-YOUR-REAL-KEY"
```

### Step B — Create a developer key

Developer tools authenticate to the gateway with a `kr-` key — the real upstream
key is never exposed.

```bash
kiri key create
```

Output:

```
kr-AbCdEfGhIjKlMnOpQrSt12
```

**Copy this value** — you will use it in every tool configuration below.

### Step C — Start the gateway

> **This command is blocking** — it occupies this terminal. Open a **new
> terminal** for all subsequent commands (§6 onwards) and leave this one running.
>
> In the new terminal, run these two commands before anything else:
>
> **macOS / Linux**
> ```bash
> cd ~/my-project
> # venv users only:
> source ~/path/to/kiri/.venv/bin/activate
> ```
>
> **Windows (PowerShell)**
> ```powershell
> cd "$HOME\my-project"
> # venv users only:
> ~/path/to/kiri/.venv\Scripts\Activate.ps1
> ```
>
> pipx users: no activation needed — `kiri` is already in your PATH.

Run from your **project directory** (`~/my-project`):

**macOS / Linux**
```bash
kiri serve
```

**Windows (PowerShell)**
```powershell
kiri serve
```

Expected output:

```
Gateway listening on http://127.0.0.1:8765
```

Verify in the second terminal:

```bash
curl http://localhost:8765/health
```

Expected: `{"status":"ok"}`

---

## 6. Send requests through the gateway

Run these in the **new terminal** you opened in Step C (the one where you ran
`cd ~/my-project`). The gateway must be running in the other terminal.

Replace `kr-AbCdEfGhIjKlMnOpQrSt12` with the key you created in Step B.

> **REDACT behaviour:** When Kiri detects protected code, it strips the
> implementation body and forwards a sanitised prompt to the upstream API — the
> LLM responds based on the stub, not the real logic. HTTP 403 (BLOCK) only
> occurs in Docker mode with Ollama.

### Request with protected code — implementation stripped before forwarding

**macOS / Linux / Git Bash**

```bash
curl -s http://localhost:8765/v1/messages \
  -H "x-api-key: kr-AbCdEfGhIjKlMnOpQrSt12" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Explain this:\ndef calculate_final_price(quantity, is_premium):\n    subtotal = 9.99 * quantity\n    discount = subtotal * 0.0325\n    tier = 2.47 if is_premium else 0.0\n    return round(subtotal - discount + tier, 2)"}]
  }'
```

**Windows (PowerShell)**

```powershell
Invoke-RestMethod -Uri http://localhost:8765/v1/messages `
  -Method POST `
  -Headers @{
    "x-api-key"          = "kr-AbCdEfGhIjKlMnOpQrSt12"
    "anthropic-version"  = "2023-06-01"
    "content-type"       = "application/json"
  } `
  -Body '{"model":"claude-haiku-4-5-20251001","max_tokens":100,"messages":[{"role":"user","content":"Explain this:\ndef calculate_final_price(quantity, is_premium):\n    subtotal = 9.99 * quantity\n    discount = subtotal * 0.0325"}]}'
```

The LLM receives a stub, not the real implementation:

```
# What Kiri actually forwarded:
"Explain this:
def calculate_final_price(quantity, is_premium):
    # [PROTECTED: implementation is confidential]
    ..."
```

The LLM cannot explain the proprietary logic because it was never sent.

To force a hard 403 block on any match (instead of redacting and forwarding),
add `action: block` to `.kiri/config.yaml`:

```yaml
action: block
```

With that setting any L2 or L1 match returns:

```json
{"error": "blocked", "reason": "symbol match: calculate_final_price, 9.99, 0.0325, 2.47"}
```

### Request without protected code — passes through

```bash
curl -s http://localhost:8765/v1/messages \
  -H "x-api-key: kr-AbCdEfGhIjKlMnOpQrSt12" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 50,
    "messages": [{"role": "user", "content": "What is 2 + 2?"}]
  }'
```

This reaches the real API and returns a normal Claude response.

### Using the Anthropic SDK (Python / Node.js)

**Python**
```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8765",
    api_key="kr-AbCdEfGhIjKlMnOpQrSt12",  # your kr- key
)
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=50,
    messages=[{"role": "user", "content": "What is 2 + 2?"}],
)
print(response.content)
```

**Node.js / TypeScript**
```typescript
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic({
  baseURL: "http://localhost:8765",
  apiKey: "kr-AbCdEfGhIjKlMnOpQrSt12",  // your kr- key
});
const response = await client.messages.create({
  model: "claude-haiku-4-5-20251001",
  max_tokens: 50,
  messages: [{ role: "user", content: "What is 2 + 2?" }],
});
console.log(response.content);
```

---

## 7. Connect your AI coding tools

The gateway is a transparent proxy — most tools only need two environment variables
(or a config file) changed. Replace `kr-AbCdEfGhIjKlMnOpQrSt12` with the key
you created in Step B of §5.

### Claude Code

Set these two variables in your shell profile (`.bashrc`, `.zshrc`, PowerShell
profile) or in a `.env` file loaded by direnv:

**macOS / Linux**
```bash
export ANTHROPIC_BASE_URL=http://localhost:8765
export ANTHROPIC_API_KEY=kr-AbCdEfGhIjKlMnOpQrSt12
```

**Windows (PowerShell — current session)**
```powershell
$env:ANTHROPIC_BASE_URL = "http://localhost:8765"
$env:ANTHROPIC_API_KEY  = "kr-AbCdEfGhIjKlMnOpQrSt12"
```

**Windows (permanent — all future sessions)**
```powershell
[Environment]::SetEnvironmentVariable("ANTHROPIC_BASE_URL", "http://localhost:8765", "User")
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY",  "kr-AbCdEfGhIjKlMnOpQrSt12", "User")
```

Then restart PowerShell and launch `claude` normally — all traffic routes through
the gateway automatically.

---

### OpenCode

Create `opencode.json` in your **project root** (next to your source files, not
inside the `kiri/` repo):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "kiri/claude-sonnet-4-6",
  "provider": {
    "kiri": {
      "name": "Kiri Gateway",
      "npm": "@ai-sdk/anthropic",
      "options": {
        "baseURL": "http://localhost:8765",
        "apiKey": "kr-AbCdEfGhIjKlMnOpQrSt12"
      },
      "models": {
        "claude-sonnet-4-6": {
          "name": "Claude Sonnet 4.6 (via Kiri)",
          "context": 200000
        }
      }
    }
  }
}
```

**Important:** replace `kr-AbCdEfGhIjKlMnOpQrSt12` with the key from `kiri key create`.

> **Why `@ai-sdk/anthropic` and not `@ai-sdk/openai-compatible`?**
> The `anthropic` package uses the `/v1/messages` endpoint, which the gateway routes
> to Anthropic. Use `@ai-sdk/openai-compatible` if your upstream key is an OpenAI key.

Start OpenCode from the **project directory** where `.kiri/` lives and
`opencode.json` is present:

```bash
opencode
```

If `opencode` is not in your PATH, run it via npx:

```bash
npx opencode@latest
```

> **Troubleshooting — "Forbidden: unauthorized"**
> This means OpenCode is reaching the gateway but the `kr-` key is rejected.
> Check that the `apiKey` in `opencode.json` exactly matches the output of
> `kiri key create` (no extra spaces or newlines). Run `kiri key list`
> to see active keys.

---

### Cursor

Add to your workspace `.env` file (Cursor loads it automatically):

```
ANTHROPIC_BASE_URL=http://localhost:8765
ANTHROPIC_API_KEY=kr-AbCdEfGhIjKlMnOpQrSt12
```

Or add to Cursor settings (`Cmd/Ctrl+Shift+P → Open Settings JSON`):

```json
{
  "terminal.integrated.env.osx":     { "ANTHROPIC_BASE_URL": "http://localhost:8765", "ANTHROPIC_API_KEY": "kr-AbCdEfGhIjKlMnOpQrSt12" },
  "terminal.integrated.env.linux":   { "ANTHROPIC_BASE_URL": "http://localhost:8765", "ANTHROPIC_API_KEY": "kr-AbCdEfGhIjKlMnOpQrSt12" },
  "terminal.integrated.env.windows": { "ANTHROPIC_BASE_URL": "http://localhost:8765", "ANTHROPIC_API_KEY": "kr-AbCdEfGhIjKlMnOpQrSt12" }
}
```

---

### Codex CLI

Codex CLI uses OpenAI-compatible endpoints. You need an OpenAI upstream key
(`.kiri/openai.key` or `OPENAI_API_KEY` env var).

**macOS / Linux**
```bash
export OPENAI_BASE_URL=http://localhost:8765/v1
export OPENAI_API_KEY=kr-AbCdEfGhIjKlMnOpQrSt12
codex "explain this function"
```

**Windows (PowerShell)**
```powershell
$env:OPENAI_BASE_URL = "http://localhost:8765/v1"
$env:OPENAI_API_KEY  = "kr-AbCdEfGhIjKlMnOpQrSt12"
codex "explain this function"
```

---

### Cline / Continue.dev

**Cline** (VS Code):
1. Open the Cline settings (gear icon in the Cline sidebar)
2. Set **API Provider** → Custom
3. Set **Base URL** → `http://localhost:8765`
4. Set **API Key** → `kr-AbCdEfGhIjKlMnOpQrSt12`

**Continue.dev** (VS Code / JetBrains) — edit `~/.continue/config.json`:
```json
{
  "models": [
    {
      "title": "Claude via Kiri",
      "provider": "anthropic",
      "model": "claude-sonnet-4-6",
      "apiBase": "http://localhost:8765",
      "apiKey": "kr-AbCdEfGhIjKlMnOpQrSt12"
    }
  ]
}
```

---

## 8. Check the audit log

Run from your **project directory** (`~/my-project`), in the same terminal as §6:

```bash
kiri log --tail 5
```

Example output:

```
2026-04-28T10:23:45.123Z  REDACT  L2  symbol match: calculate_final_price, 9.99  sim=0.000  [calculate_final_price]
2026-04-28T10:24:12.456Z  PASS    L1  below threshold  sim=0.031
```

Filter by decision:

```bash
kiri log --decision REDACT --since today
kiri log --decision BLOCK --since today
```

Explain the last intercepted request:

```bash
kiri explain
```

Show the full prompt as it was forwarded to the LLM (stubs replacing protected code):

```bash
kiri explain --show-redacted
```

---

## 9. Protect a symbol directly (no indexing needed)

Run from your **project directory** (`~/my-project`):

```bash
kiri add @calculate_final_price
```

L2 now intercepts any prompt containing the exact string `calculate_final_price`:

```bash
kiri inspect "please refactor calculate_final_price to use a config object"
```

```
Decision   : REDACT
Reason     : symbol match: calculate_final_price
Similarity : 0.0000
Symbols    : calculate_final_price
```

---

## 10. Remove protection

```bash
kiri rm pricing.py
kiri rm @calculate_final_price
```

---

## Configuration reference

All settings live in `.kiri/config.yaml` (created automatically on first run):

```yaml
# .kiri/config.yaml
similarity_threshold: 0.75    # grace zone starts here (L3 applied if available)
hard_block_threshold: 0.90    # L1 hard REDACT above this
action: sanitize              # "sanitize" = REDACT (strip + forward) | "block" = HTTP 403
proxy_port: 8765
ollama_model: qwen2.5:3b      # used only in Docker mode
symbol_min_length: 9          # minimum symbol length for fallback (no Ollama)
ollama_timeout_seconds: 10.0  # L3 classifier request timeout
```

---

## Production setup (Docker + Ollama)

The local `kiri serve` is sufficient for a single developer. For a team deployment
with the full L3 Ollama classifier, use Docker Compose.

### What `docker compose up` does

`docker-compose.yml` defines three services:

| Service | What it does |
|---------|-------------|
| `kiri` | Builds the Python image from `kiri/Dockerfile`, exposes port 8765 |
| `ollama` | Runs the Ollama inference server (CPU or GPU) |
| `ollama-pull` | One-shot: pulls `qwen2.5:3b` once Ollama is healthy, then exits |

`kiri` waits for `ollama-pull` to complete before starting — so the classifier
model is always ready when the proxy accepts its first request.

### Setup steps

Run from the **repo root** (where `kiri/docker-compose.yml` lives):

```bash
# 1. Store the real Anthropic key as a Docker secret
#    This file is gitignored and never visible via `docker inspect`
mkdir -p kiri/.kiri
echo "sk-ant-YOUR-REAL-KEY" > kiri/.kiri/upstream.key
chmod 600 kiri/.kiri/upstream.key

# 2. Build the image and start all services
#    First run: downloads qwen2.5:3b (~2 GB) — takes a few minutes
cd kiri
docker compose up -d

# 3. Wait for healthy status
docker compose ps      # STATUS should show "healthy" for the kiri service

# 4. Generate a key for each developer
docker compose exec kiri kiri key create
# → kr-xxxxxxxxxxxxxxxxxxxxxxxx
```

### Connect developer tools

Each developer adds these to their shell profile:

```bash
export ANTHROPIC_BASE_URL=http://localhost:8765
export ANTHROPIC_API_KEY=kr-...    # the kr- key, NOT the real sk-ant- key
```

### Useful Docker commands

```bash
# View kiri logs
docker compose logs -f kiri

# View audit log inside the container
docker compose exec kiri kiri log --tail 20

# Stop everything
docker compose down

# Rebuild after source changes
docker compose up -d --build kiri
```

---

## What gets committed to git

```
.kiri/secrets      ✅  which files and symbols are protected
.kiri/config.yaml  ✅  thresholds and settings
.kiri/index/       ❌  rebuilt locally (add to .gitignore)
.kiri/keys/        ❌  per-developer (add to .gitignore)
.kiri/upstream.key ❌  real API key (add to .gitignore)
```

---

## New developer joining the team

If your team already has the gateway set up, you only need to:

**1. Install the gateway CLI** (same as §1 above)

Clone the repo and install with pipx so `kiri` is in your PATH automatically:

**macOS / Linux**
```bash
git clone https://github.com/PaoloMassignan/kiri kiri
cd kiri
pip install --user pipx && python3 -m pipx ensurepath
# close and reopen the terminal, then:
pipx install --editable ./kiri
```

**Windows (PowerShell)**
```powershell
git clone https://github.com/PaoloMassignan/kiri kiri
cd kiri
pip install --user pipx; python -m pipx ensurepath
# close and reopen PowerShell, then:
pipx install --editable .\kiri
```

Verify: `kiri --help` — if not found, close and reopen the terminal once more.

> **Alternative — venv:** `cd kiri && python3 -m venv .venv && source .venv/bin/activate && pip install -e .`
> (Windows: `.venv\Scripts\Activate.ps1` instead of `source ...`)
> You must activate the venv **in every new terminal** before running `kiri`.

**2. Start the gateway** (from your project directory)

```bash
kiri serve
```

Or via Docker:

```bash
docker compose up -d
docker compose ps   # wait until kiri shows "healthy"
```

**3. Generate your personal key**

```bash
kiri key create
# → kr-xxxxxxxxxxxxxxxxxxxxxxxx
```

**4. Set your environment variables**

**macOS / Linux**
```bash
cp .env.example .env
# edit .env — replace kr-your-key-here with your actual kr- key
```

**Windows (PowerShell)**
```powershell
Copy-Item .env.example .env
# open .env in your editor and replace kr-your-key-here with your actual key
```

From this point, all your AI coding tools route through the gateway automatically — no
further setup required.
