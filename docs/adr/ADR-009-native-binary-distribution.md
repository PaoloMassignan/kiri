# ADR-009: Native binary distribution (no Docker, no Ollama)

## Status
Proposed

## Context

The current distribution requires Docker Desktop and runs Ollama as a sidecar container.
This creates two adoption barriers:

1. **Docker Desktop** is a heavy dependency (~500MB, requires admin rights, adds overhead).
   Many enterprise IT policies restrict or ban Docker Desktop on developer workstations.
   For solo developers or small teams, the install experience is disproportionate.

2. **Ollama as a separate service** adds a second process the user must manage,
   increases resource consumption, and complicates startup scripts.

Docker's role in Kiri is twofold:
- Cross-platform deployment and automatic restart
- Key isolation: the real `sk-ant-` key lives inside the container, invisible to the developer

Both goals can be achieved without Docker:
- **Deployment**: a single compiled binary distributed as a native installer
- **Key isolation**: OS-level service account (same isolation model as Postgres, nginx, Ollama itself)

Ollama's role in Kiri is:
- L3 classifier (grace zone 0.75–0.90)
- Auto-generation of redaction summaries

Both can be handled in-process via `llama-cpp-python` (Python bindings for llama.cpp),
eliminating the need for a separate service while keeping the same GGUF models.

## Decision

Ship Kiri as a **self-contained native binary** with the following properties:

- **Single installer** per platform (Linux `.deb`/`.rpm`, macOS `.pkg`, Windows `.msi`)
- **All dependencies bundled**: Python runtime, sentence-transformers, llama-cpp-python, ChromaDB
- **L3 active by default**: GGUF model (`qwen2.5:3b`) downloaded at first start, stored under the service account's home (`/var/lib/kiri/models/`)
- **L3 can be disabled** via `kiri install --no-local-ai` for air-gapped or resource-constrained environments
- **Key isolation via OS service account**: the service runs as a dedicated system user (`kiri`); the upstream key file is owned by that user (mode 600); developers cannot read it
- **API surface unchanged**: still listens on `localhost:8765`, same Anthropic/OpenAI/Ollama protocol; zero changes to Claude Code or any client tool

Install flow:
```bash
# One-time admin setup
sudo kiri install         # creates kiri system user, installs service, prompts for sk-ant- key
                           # downloads GGUF model on first start (~2 GB)

# Per-developer
kiri key create           # generates a kr- key for the developer
```

This ADR partially supersedes **ADR-003** (Docker secrets → OS user isolation).

## Consequences

**Positive:**
- No Docker Desktop required — onboarding reduces to a single installer download
- L3 active by default — full filter pipeline out of the box, not an optional extra
- Key isolation maintained via OS user separation (same model used by Postgres, nginx, Ollama)
- Binary is self-contained — works offline after first model download
- Smaller operational footprint: one process instead of two containers

**Negative:**
- Binary size ~200–400 MB (Python runtime + ML libraries bundled)
- First start requires internet access to download the GGUF model (~2 GB)
  → mitigatable with `--model-path` flag pointing to a pre-downloaded file
- Key isolation is weaker than Docker namespaces on multi-user systems where
  developers have `sudo` access — same caveat as ADR-003, different attack surface
- Windows Service account setup is more complex than Linux/macOS equivalents

**Derived constraints:**
- The GGUF model and the upstream key must both be stored under the `kiri` service account's directory, not in the project `.kiri/` folder
- `llama-cpp-python` must be compiled with the appropriate backend at build time (CPU, CUDA, Metal) — likely requires separate binaries per platform/accelerator

## Alternatives considered

**Keep Docker, reduce friction (Docker-in-Docker, Rancher Desktop, etc.):**
- Does not remove the Docker Desktop requirement — eliminated

**Ship as a Python package (`pip install kiri`) with Ollama as external dependency:**
- Python version conflicts, no key isolation, Ollama still separate — worse DX than current

**Use OS keychain (macOS Keychain, Windows Credential Manager) instead of service account:**
- Does not isolate the key from the logged-in developer — they can read their own keychain
- Service account isolation is strictly stronger for this threat model
