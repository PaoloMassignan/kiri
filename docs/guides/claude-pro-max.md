# How to connect Claude Code (Pro/Max) to Kiri

Claude Code with a **Claude Pro or Max subscription** authenticates via OAuth —
there is no static `sk-ant-` API key to store in the gateway. Kiri supports
this via **OAuth passthrough mode**: the gateway accepts the OAuth session token
directly, runs the full filter pipeline, and forwards the request with the
original token unchanged.

> **Security note:** In this mode the dual-key bypass-prevention guarantee does
> not apply — a developer can bypass the gateway by unsetting `ANTHROPIC_BASE_URL`.
> If bypass-prevention is a hard requirement, use an Anthropic API key account instead.

---

## Prerequisites

- Kiri gateway running (`docker compose up -d`)
- Claude Code installed and authenticated with your Pro/Max account (`claude login`)

---

## Step 1 — Enable OAuth passthrough in config

Edit `.kiri/config.yaml` in your project root:

```yaml
oauth_passthrough: true
```

If the file doesn't exist yet, create it:

```bash
mkdir -p .kiri
echo "oauth_passthrough: true" >> .kiri/config.yaml
```

Restart the gateway to pick up the change:

```bash
docker compose restart
```

---

## Step 2 — Point Claude Code at the gateway

Add these two lines to your shell profile (`~/.zshrc`, `~/.bashrc`, or `~/.profile`):

```bash
export ANTHROPIC_BASE_URL=http://localhost:8765
```

That's it. You do **not** set `ANTHROPIC_API_KEY` — Claude Code continues to use its
own OAuth session. The `ANTHROPIC_BASE_URL` redirect is enough.

Reload your shell:

```bash
source ~/.zshrc   # or ~/.bashrc
```

---

## Step 3 — Verify

```bash
claude "say hello"
```

You should get a normal response. Check the audit log to confirm traffic is going
through the gateway:

```bash
kiri log --tail 5
```

You should see a recent `PASS` entry with `key_id: oauth-passthrough`.

---

## How it works

```
Claude Code (OAuth session)
  │  Authorization: Bearer sk-ant-oat01-xxx
  │  ANTHROPIC_BASE_URL=http://localhost:8765
  ▼
Kiri gateway (oauth_passthrough: true)
  ├─ recognises sk-ant- token → passthrough mode
  ├─ runs filter pipeline (L1 / L2 / L3)
  ├─ PASS  → forwards with original Bearer token
  ├─ REDACT → replaces function bodies, forwards
  └─ BLOCK  → returns permission_error (no forwarding)
  ▼
api.anthropic.com
```

The gateway never stores or logs the OAuth token beyond the in-flight request.
The audit log records `key_id: oauth-passthrough` for every request in this mode.

---

## Shared team gateway

If your admin runs a shared Kiri gateway, enable `oauth_passthrough: true` on the
server and distribute the gateway URL. Each developer connects with:

```bash
./install/macos/connect.sh    # macOS
./install/linux/connect.sh    # Linux
```

When prompted for a `kr-` key, leave it blank — the connect script will offer the
OAuth passthrough option.

> If your team requires bypass-prevention, use API key mode: each developer gets a
> personal `kr-` key and the admin stores a real `sk-ant-` key in the gateway.
