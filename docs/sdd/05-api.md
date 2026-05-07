# SDD-05: API Reference

## HTTP Proxy API

The gateway exposes the subset of the Anthropic and OpenAI API needed
for Claude Code, Cursor, and Copilot. Clients do not need to know they are
talking to a proxy.

### Authentication

All endpoints require an `Authorization: Bearer kr-xxx` header.
An invalid or expired `kr-` key returns HTTP 401.

**OAuth passthrough mode** (`oauth_passthrough: true` in `.kiri/config.yaml`):
Requests carrying an Anthropic token (`sk-ant-` prefix) are also accepted. The
gateway runs the full filter pipeline and forwards the request with the original
token unchanged. The dual-key bypass-prevention guarantee does not apply in this mode.
Intended for Claude Code users authenticated via Claude Pro/Max (OAuth).

```yaml
# .kiri/config.yaml
oauth_passthrough: true   # default: false
```

---

### POST /v1/messages (Anthropic)

Main endpoint for Claude Code.

**Request:** identical to the [Anthropic Messages API](https://docs.anthropic.com/en/api/messages).

**Response (PASS):** upstream response forwarded unchanged (streaming or batch).

**Response (BLOCK):**
```json
HTTP 200
{
  "type": "error",
  "error": {
    "type": "permission_error",
    "message": "Prompt contains protected IP: RiskScorer (src/engine/risk_scorer.py)"
  }
}
```

Note: HTTP 200, not 403 — Claude Code handles Anthropic-shaped errors better.

**Response (BLOCK, SSE streaming):**
```
event: error
data: {"type":"error","error":{"type":"permission_error","message":"..."}}
```

**Response (REDACT):** upstream receives the redacted prompt and the response
is forwarded unchanged. The client sees no difference.

---

### GET /v1/models (Anthropic)

Model list request. Authenticated and then forwarded to upstream.
Does not pass through the filter pipeline.

---

### POST /v1/chat/completions (OpenAI)

For Cursor, GitHub Copilot, and other OpenAI-compatible tools.

**Request:** [OpenAI Chat Completions](https://platform.openai.com/docs/api-reference/chat) format.

**Prompt extraction:** the gateway concatenates all `content` from messages
with role `user` and `assistant` and applies the filter pipeline to the resulting text.

**Response (PASS):** upstream response forwarded unchanged.

**Response (BLOCK):**
```json
HTTP 200
{
  "error": {
    "message": "Prompt contains protected IP: RiskScorer",
    "type": "permission_error",
    "code": "permission_denied"
  }
}
```

---

### Middleware

**Body size limit (REQ-S-008):**
```
Content-Length > 10MB → HTTP 413
{"error": "request_too_large"}
```
Applied before authentication to prevent DoS.

**Rate limit (REQ-F-008):**
```
kr- key exceeds sliding window → HTTP 429
{"error": "rate_limit_exceeded"}
```

---

## CLI

The gateway CLI is invoked with `kiri <command>`.

### `kiri add <target>`

Adds a file path, directory rule, glob pattern, or symbol to the protected set.

```bash
kiri add src/engine/risk_scorer.py   # single file
kiri add src/engine/                 # all files in directory, recursively
kiri add "src/**/*.py"               # glob pattern
kiri add @RiskScorer                 # explicit symbol (L2, no reindex needed)
```

Directory and glob rules are stored as `@glob <pattern>` entries in `.kiri/secrets`. The watcher expands them on startup and re-expands every 60 seconds to pick up new files automatically.

**Exit code:** 0 OK, 1 error (path not found, path traversal).

---

### `kiri rm <target>`

Removes a file path, directory rule, glob pattern, or symbol.

```bash
kiri rm src/engine/risk_scorer.py    # single file
kiri rm src/engine/                  # removes @glob rule, purges indexed vectors
kiri rm "src/**/*.py"                # removes @glob rule
kiri rm @RiskScorer                  # symbol
```

On glob removal, all files previously indexed from that rule are purged from the vector and symbol stores, unless the same file is also individually listed in secrets.

**Exit code:** 0 OK (even if it did not exist), 1 error.

---

### `kiri status`

Shows the protection status.

```
=== Gateway Protection Status ===

Protected directories/globs (1):
  @glob src/engine/  (8 file(s))

Protected files (1):
  src/billing/token_bucket.py

Explicit symbols (3):
  @RiskScorer
  @sliding_window_dedup
  @DataFlowEngine

Indexed chunks : 47
Known symbols  : 12
```

---

### `kiri inspect [text] [--file path]`

Dry-run of the filter pipeline.

```bash
kiri inspect "how does RiskScorer work?"
kiri inspect --file /tmp/prompt.txt    # avoids shell history
```

Output:
```
Decision : BLOCK
Level    : L2
Reason   : symbol match: RiskScorer
Similarity: 0.871
Symbols  : RiskScorer
```

---

### `kiri log [--tail N] [--decision D] [--since DATE]`

Shows the last N lines of the audit log.

```bash
kiri log                              # last 50
kiri log --tail 100
kiri log --decision BLOCK
kiri log --decision BLOCK --since today
kiri log --since 2026-04-01
```

---

### `kiri index [path] [--all]`

Indexes immediately without the kiri server.

```bash
kiri index src/engine/risk_scorer.py
kiri index --all                      # all files in secrets
```

---

### `kiri key create [--expires-in DAYS]`

Generates a new `kr-` key.

```bash
kiri key create
kiri key create --expires-in 90
```

Output: the key on stdout.

---

### `kiri key list`

Shows active keys with their expiry dates.

```
kr-a1b2c3...  expires 2026-07-01
kr-d4e5f6...  (no expiry)
```

---

### `kiri key revoke <key>`

Revokes a key.

```bash
kiri key revoke kr-a1b2c3...
```

**Exit code:** 0 OK, 1 key not found.

---

### `kiri serve`

Starts the proxy server.

```bash
kiri serve
# Gateway listening on http://127.0.0.1:8765
```

Fixed binding to `127.0.0.1` (never `0.0.0.0`). See REQ-S-005.
