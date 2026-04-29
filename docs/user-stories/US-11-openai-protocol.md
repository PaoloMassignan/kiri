# US-11 — OpenAI protocol compatibility

## Description

**As** a developer using Cursor, Copilot, or any tool with an OpenAI-compatible API,
**I want** the gateway to protect my non-Claude calls as well,
**so that** protection of company code applies regardless of the tool I use.

---

## Scenario

The developer uses Cursor connected to OpenAI. They configure the base URL:

```bash
# .env
OPENAI_BASE_URL=http://localhost:8765
OPENAI_API_KEY=kr-<gateway-key>
```

Cursor sends a request to the gateway in OpenAI format:

```json
POST /v1/chat/completions
{
  "model": "gpt-4o",
  "messages": [
    {"role": "user", "content": "explain pricing_spread in calibrator.py"}
  ]
}
```

The gateway extracts the prompt, passes it through L1/L2/L3, and blocks:

```json
HTTP 403
{"error": "blocked", "reason": "L2 symbol match: pricing_spread"}
```

If the prompt is safe, the gateway forwards it to the configured upstream OpenAI.

---

## Expected behaviour

- `/v1/chat/completions` uses the same filter pipeline as `/v1/messages`
- Prompt extraction works on both `content` as a string and as a content array (multipart)
- The upstream is configurable: OpenAI, Azure OpenAI, Ollama, or any compatible endpoint
- The upstream key (`OPENAI_API_KEY`) lives only in the container, never exposed
- Streaming (`stream: true`) is supported as with the Anthropic protocol

---

## Acceptance criteria

- [ ] `POST /v1/chat/completions` with safe prompt → 200 forwarded upstream
- [ ] `POST /v1/chat/completions` with protected symbol → 403 blocked
- [ ] Content as string and as array `[{"type":"text","text":"..."}]` are both handled
- [ ] Streaming with `stream: true` does not bypass the filter
- [ ] The upstream OpenAI is configurable via the `OPENAI_UPSTREAM_URL` env var
- [ ] Anthropic and OpenAI keys coexist — the gateway selects the upstream based on the path

---

## Notes

The OpenAI protocol is structurally different from Anthropic:
- endpoint: `/v1/chat/completions` vs `/v1/messages`
- model field: `model` in both
- content: `messages[].content` (can be a string or an array of parts)
- upstream key: `Authorization: Bearer sk-...` vs `x-api-key: sk-ant-...`

Extraction and forwarding logic should be separated per protocol in `src/proxy/protocols/`.
The filter pipeline is shared — it does not depend on the protocol.
