# US-16 — Claude Code OAuth passthrough (Pro/Max)

## Description

**As** a developer using Claude Code with a Claude Pro/Max subscription (OAuth),
**I want** Kiri to intercept and filter my LLM calls without requiring an Anthropic API key,
**so that** I can protect my proprietary code even though I don't have a `sk-ant-` key to give to the gateway.

---

## Background

Claude Code with a Pro/Max subscription authenticates via OAuth session tokens
(`sk-ant-oat01-` prefix), not via a static API key. The dual-key model (kr- + sk-ant-)
cannot be applied because there is no upstream API key to store in the gateway.

In OAuth passthrough mode the gateway:
1. Accepts the original OAuth Bearer token from Claude Code
2. Runs the full filter pipeline (L1/L2/L3) — IP protection is unchanged
3. Forwards the request to Anthropic with the original token unchanged

The bypass-prevention guarantee (dual-key model) does not apply in this mode —
the developer already holds the real upstream credential. The tradeoff is documented.

---

## Interaction

Developer sets `ANTHROPIC_BASE_URL=http://localhost:8765` in their environment
(same as API key mode). Claude Code continues to use its own OAuth session. No other
change required.

Enable in `.kiri/config.yaml`:

```yaml
oauth_passthrough: true
```

---

## Expected behaviour

- Requests carrying an Anthropic token (`sk-ant-`) reach the gateway and pass through
  the filter pipeline
- PASS requests are forwarded to `api.anthropic.com` with the original token
- BLOCK requests are rejected with the standard error format
- REDACT requests are redacted and forwarded with the original token
- `kr-` key requests continue to work normally regardless of this setting
- With `oauth_passthrough: false` (default), Anthropic tokens are rejected with HTTP 401

---

## Acceptance criteria

- [x] `oauth_passthrough: false` (default): requests with `sk-ant-` token return HTTP 401
- [x] `oauth_passthrough: true`: requests with `sk-ant-oat01-` token are accepted
- [x] `oauth_passthrough: true`: requests with `sk-ant-api03-` token are accepted
- [x] filter pipeline runs on every OAuth passthrough request
- [x] BLOCK decision returns the standard block response, not HTTP 401
- [x] forwarded request uses `Authorization: Bearer <original_token>`, not `x-api-key`
- [x] audit log records `key_id = "oauth-passthrough"` for passthrough requests
- [x] `kr-` key requests are unaffected when `oauth_passthrough: true`

---

**Status:** Done — `src/keys/manager.py` (`is_oauth_token`), `src/proxy/server.py` (passthrough auth flow), `src/proxy/forwarder.py` (Bearer auth for OAuth tokens), `src/config/settings.py` (`oauth_passthrough` flag).

---

## Security note

OAuth passthrough mode is explicitly weaker than the default dual-key model:
a developer can bypass Kiri by unsetting `ANTHROPIC_BASE_URL`, and the gateway
cannot prevent it. This is documented in the config and in the audit log.

For teams that require bypass-prevention, the dual-key model (API key mode) remains
the recommended configuration.
