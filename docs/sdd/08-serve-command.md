# `kiri serve` — Gateway startup and key management

> **Related:** [ADR-003](../adr/ADR-003-docker-secrets.md) (Docker key isolation),
> [ADR-009](../adr/ADR-009-native-binary-distribution.md) (native distribution),
> [SDD-07](07-distribution.md) (installer and service setup)

---

## Overview

`kiri serve` starts the FastAPI proxy on `127.0.0.1:8765` (never `0.0.0.0`).
It is the entry point for both the Docker distribution (invoked via `uvicorn` in the
Dockerfile CMD) and the native distribution (invoked by the OS service manager).

```
kiri serve [--port <n>] [--upstream-key-file <path>]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--port` / `-p` | `8765` (from config) | Override the listening port |
| `--upstream-key-file` | — | Path to the upstream API key file; sets `KIRI_UPSTREAM_KEY_FILE` |

---

## Upstream key lookup chain

`KeyManager.get_upstream_key()` resolves the real API key (`sk-ant-…`) via a
four-tier chain, evaluated in order:

```
Tier 0  KIRI_UPSTREAM_KEY_FILE env var  ← native distribution (systemd sets this)
        ↓ (missing or empty)
Tier 1  /run/secrets/anthropic_key      ← Docker secret (never in docker inspect)
        ↓ (missing or empty)
Tier 2  {workspace}/.kiri/upstream.key  ← local dev without Docker
        ↓ (missing or empty)
Tier 3  ANTHROPIC_API_KEY env var       ← last resort / CI
        ↓ (missing or empty)
        → MissingUpstreamKeyError
```

Each tier is tried only if the previous one is absent or empty.

### Tier 0 — native distribution

The OS service manager sets `KIRI_UPSTREAM_KEY_FILE` to the path of the key file
owned by the `kiri` service account:

```ini
# /etc/systemd/system/kiri.service
Environment=KIRI_UPSTREAM_KEY_FILE=/var/lib/kiri/upstream.key
```

```xml
<!-- /Library/LaunchDaemons/dev.kiri.plist -->
<key>KIRI_UPSTREAM_KEY_FILE</key><string>/var/lib/kiri/upstream.key</string>
```

The file is `chmod 600`, owned by the `kiri` system user — the developer process
cannot read it. The env var can also be overridden on the command line:

```bash
kiri serve --upstream-key-file /custom/path/upstream.key
```

### Tier 1 — Docker secret

In Docker, the key is mounted at `/run/secrets/anthropic_key` via Docker secrets
(see ADR-003). It is not visible in `docker inspect` or `docker exec env`.

### Tier 2 — local dev

During local development (no Docker, no service), the key can be placed in the
workspace:

```bash
echo "sk-ant-YOUR-KEY" > .kiri/upstream.key
chmod 600 .kiri/upstream.key
```

### Tier 3 — env var

```bash
export ANTHROPIC_API_KEY=sk-ant-YOUR-KEY
kiri serve
```

---

## Port binding

`kiri serve` always binds to `127.0.0.1` (REQ-S-005 — never `0.0.0.0`).
The Docker distribution uses `0.0.0.0` inside the container because Docker's port
forwarding requires it; the host-side binding in `docker-compose.yml` is restricted
to `127.0.0.1:8765`. The native binary never needs this indirection.

The default port is `8765`, overridable in config or via `--port`:

```bash
kiri serve --port 9000
```

---

## Startup sequence

```
kiri serve
  │
  ├─ apply --upstream-key-file → os.environ["KIRI_UPSTREAM_KEY_FILE"]
  ├─ Settings.load()           → reads .kiri/config.yaml (or KIRI_CONFIG)
  ├─ create_gateway_app()
  │    ├─ make_llm_backend()   → OllamaBackend or LlamaCppBackend (from settings)
  │    ├─ Watcher.start()      → background indexer + file watcher
  │    └─ FastAPI app
  └─ uvicorn.run(host="127.0.0.1", port=...)
```

---

## Service integration (native distribution)

The OS service manager invokes `kiri serve` directly:

```ini
# systemd
ExecStart=/usr/bin/kiri serve
Environment=KIRI_UPSTREAM_KEY_FILE=/var/lib/kiri/upstream.key
Environment=KIRI_CONFIG=/var/lib/kiri/config.yaml
Environment=WORKSPACE=/var/lib/kiri/workspace
```

```xml
<!-- launchd -->
<key>ProgramArguments</key>
<array>
  <string>/usr/local/bin/kiri</string>
  <string>serve</string>
</array>
```

The developer interacts with a running Kiri via the same CLI commands (`kiri status`,
`kiri add`, etc.) pointing at their project workspace — the service reads the protected
files from the developer's workspace directory, not from `/var/lib/kiri/`.
