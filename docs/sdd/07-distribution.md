# Distribution — Native Binary

> **Context:** This document describes the native binary distribution of Kiri.
> For the Docker-based distribution see [02-architecture.md](02-architecture.md).
> For the decision rationale see [ADR-009](../adr/ADR-009-native-binary-distribution.md).

---

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Developer                            │
│                                                             │
│   Claude Code / Cursor / Copilot                            │
│   (ANTHROPIC_BASE_URL=http://localhost:8765)                │
│   (ANTHROPIC_API_KEY=kr-xxxx)                               │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP :8765
                               ▼
               ┌───────────────────────────────┐
               │  kiri  (OS system service)     │
               │  runs as: kiri system user     │
               │                               │
               │  FastAPI proxy                │
               │  Filter pipeline (L1+L2+L3)   │
               │  File watcher + indexer       │
               │  llama-cpp-python (in-process) │
               └───────────────┬───────────────┘
                               │ reads (read-only)
               ┌───────────────▼───────────────┐
               │  /var/lib/kiri/  (kiri user)  │
               │    upstream.key   (mode 600)   │
               │    models/qwen2.5-3b.gguf     │
               │    index/                     │
               └───────────────────────────────┘
                               │ mounts workspace
               ┌───────────────▼───────────────┐
               │  Project directory             │
               │    .kiri/secrets  ← git ✅     │
               │    .kiri/config.yaml ← git ✅  │
               └───────────────────────────────┘
```

---

## Installer

### Platforms

| Platform | Format | Service manager |
|----------|--------|-----------------|
| Linux (Debian/Ubuntu) | `.deb` | systemd |
| Linux (RHEL/Fedora) | `.rpm` | systemd |
| macOS | `.pkg` | launchd |
| Windows | `.msi` | Windows Service |

### Install flow

```bash
sudo kiri install [--no-local-ai] [--model-path <path>] [--port <port>]
```

Steps performed by `kiri install`:

1. Create system user `kiri` (non-interactive, no login shell)
2. Create `/var/lib/kiri/` owned by `kiri:kiri`, mode 750
3. Prompt for upstream key (`sk-ant-...`), write to `/var/lib/kiri/upstream.key` (mode 600, owned by kiri)
4. Install and enable the system service (systemd unit / launchd plist / Windows Service)
5. On first service start: download GGUF model to `/var/lib/kiri/models/` unless `--no-local-ai`

```bash
# Per-developer (no sudo required)
kiri key create      # generates kr- key, stores in ~/.kiri/keys/
kiri key list
kiri key revoke kr-...
```

### Flags

| Flag | Effect |
|------|--------|
| `--no-local-ai` | Disables L3 and auto-summaries; L1+L2 only |
| `--model-path <path>` | Use a pre-downloaded GGUF file (air-gapped install) |
| `--port <n>` | Override default port 8765 |

---

## Key isolation

The upstream key is isolated via OS user separation — the same model used by
Postgres, nginx, and Ollama.

```
/var/lib/kiri/upstream.key
  owner: kiri
  group: kiri
  mode:  600
```

A developer user cannot read this file without `sudo`. The `kiri` service process
reads it at startup and holds it in memory; it never writes it to logs or the
audit trail.

**Comparison to Docker secrets:**

| Property | Docker secrets | OS service account |
|----------|---------------|-------------------|
| Not in `inspect`/`env` | ✅ | ✅ (no equivalent) |
| Not readable by developer | ✅ | ✅ (file mode 600, different user) |
| Requires container runtime | ✅ | ❌ |
| Works on systems without Docker | ❌ | ✅ |
| Survives reboot without Docker | requires restart policy | ✅ (service manager) |

---

## L3 — in-process via llama-cpp-python

In the Docker distribution, L3 and auto-summaries are handled by a running Ollama
sidecar. In the native binary, the same GGUF models run in-process via
`llama-cpp-python` (Python bindings for llama.cpp).

```
Filter pipeline (L3 grace zone):
  prompt → llama_cpp.Llama (in-process) → "extract_ip" | "pass"

Redaction summaries:
  symbol + stub → llama_cpp.Llama (in-process) → human-readable description
```

**Model:** `qwen2.5:3b` in GGUF format (~2 GB), same model used in Docker distribution.

**Storage:** `/var/lib/kiri/models/qwen2.5-3b-q4.gguf` (owned by `kiri` user).
Developers cannot read or exfiltrate the model file.

**Acceleration:** `llama-cpp-python` is compiled with backend support per platform:

| Platform | Backend |
|----------|---------|
| Linux (CPU) | AVX2 |
| Linux (NVIDIA) | CUDA |
| macOS (Apple Silicon) | Metal |
| Windows (CPU) | AVX2 |

The installer ships the appropriate binary. No manual configuration required.

**`--no-local-ai` mode:** `llama-cpp-python` is not loaded. L3 is absent;
the grace zone (0.75–0.90) degrades to fail-open per ADR-004.
Auto-summaries fall back to the generic stub
`# [PROTECTED: implementation is confidential]`.

---

## Binary composition

The binary is built with PyInstaller (or Nuitka) and bundles:

| Component | Size (approx.) |
|-----------|---------------|
| Python runtime | ~15 MB |
| FastAPI + httpx + uvicorn | ~10 MB |
| sentence-transformers + model (`all-MiniLM-L6-v2`) | ~90 MB |
| ChromaDB embedded | ~20 MB |
| llama-cpp-python (runtime only, no model) | ~30 MB |
| Kiri source | ~5 MB |
| **Total** | **~170 MB** |

The GGUF model (~2 GB) is downloaded separately at first start and stored
under `/var/lib/kiri/models/`. It is not bundled in the installer.

---

## Service management

### Linux (systemd)

```ini
# /etc/systemd/system/kiri.service
[Unit]
Description=Kiri AI Gateway
After=network.target

[Service]
Type=simple
User=kiri
Group=kiri
ExecStart=/usr/bin/kiri serve
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now kiri
sudo systemctl status kiri
journalctl -u kiri -f
```

### macOS (launchd)

```xml
<!-- /Library/LaunchDaemons/dev.kiri.plist -->
<key>UserName</key><string>_kiri</string>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
```

```bash
sudo launchctl load /Library/LaunchDaemons/dev.kiri.plist
```

### Windows (Service)

```powershell
kiri install          # registers the Windows Service
Start-Service kiri
Get-Service kiri
```

---

## Upgrade

```bash
# Download new installer, run:
sudo kiri upgrade
# → stops service, replaces binary, restarts service
# → upstream.key and models are preserved
```

---

## Air-gapped installation

For environments without internet access:

```bash
# On an internet-connected machine:
kiri download-model --output qwen2.5-3b-q4.gguf

# Transfer the installer and the model file to the target machine, then:
sudo kiri install --model-path ./qwen2.5-3b-q4.gguf
```

---

## Comparison: Docker vs Native

| | Docker distribution | Native binary |
|--|--------------------|----|
| Prerequisites | Docker Desktop | Nothing |
| Install command | `docker compose up -d` | `sudo kiri install` |
| Key isolation | Docker secrets | OS service account (mode 600) |
| L3 | Ollama sidecar (separate process) | llama-cpp-python (in-process) |
| L3 default | opt-in | **on by default** |
| Binary size | Image ~1.5 GB | Installer ~170 MB + model ~2 GB |
| Restart on reboot | `restart: always` | systemd/launchd/Windows Service |
| Multi-user isolation | Container namespace | OS user separation |
| Target | Teams with Docker infra | Everyone else |
