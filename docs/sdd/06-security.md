# SDD-06: Security Design

## Threat Model

The gateway protects against two classes of actors:

| Actor | Motivation | Methods |
|--------|-------------|--------|
| **Unauthorized developer** | Wants to use the gateway without going through the controls | Calls Anthropic directly without the proxy; creates their own gateway proxy |
| **Authorized developer who wants to exfiltrate code** | Wants to extract proprietary IP via LLM | Crafts prompts that bypass the filter; uses encoding, obfuscation, paraphrasing |

The system does not protect against:
- Physical attack on the host filesystem (access to `.kiri/upstream.key`)
- Developer who manually copies the code
- LLM that memorizes and reproduces code in future conversations (out-of-scope)

---

## Implemented controls

### 1. Gateway key authentication (REQ-S-001)

Every request must carry a valid, non-expired `kr-` key.
If the developer bypasses the proxy and uses the `kr-` key directly with Anthropic
→ HTTP 401 (the key is not recognized by Anthropic).

See [ADR-005](../adr/ADR-005-gateway-key-model.md).

### 2. Upstream key isolation (REQ-S-002)

The real Anthropic key (`sk-ant-xxx`) is mounted as a Docker secret
at `/run/secrets/anthropic_key`. It does not appear in `docker inspect`, `docker exec env`,
or in logs.

See [ADR-003](../adr/ADR-003-docker-secrets.md).

### 3. Localhost binding (REQ-S-005)

The proxy listens on `127.0.0.1:8765`, not on `0.0.0.0`.
Prevents other hosts on the same LAN from using the gateway.

### 4. Body size limit (REQ-S-008)

Requests > 10MB are rejected with HTTP 413 before authentication.
Prevents resource exhaustion via oversized requests.

### 5. File permissions (REQ-S-007)

Files containing sensitive data (`secrets`, `symbols.json`, `summaries.json`) are
written with `chmod(0o600)` on POSIX systems. On Windows this operation is silently skipped
(the NTFS filesystem uses ACLs, not POSIX mode).

### 6. Path traversal protection (REQ-S-009)

`kiri add` resolves the provided path and verifies it is within the workspace root.
A path like `../../etc/passwd` is rejected.

### 7. Pre-commit hook (REQ-S-006)

The hook `scripts/hooks/pre-commit` scans staged diff lines for the pattern
`kr-[A-Za-z0-9_-]{20,}`. If found, it blocks the commit.

One-time installation: `bash scripts/install-hooks.sh`.

If a `kr-` key is already in git history, use `git filter-repo` to remove it
and revoke the key with `kiri key revoke`.

### 8. Read-only volume for the workspace

```yaml
volumes:
  - .:/workspace:ro           # source in read-only
  - ./.gateway:/workspace/.gateway  # only .gateway in read-write
```

The container cannot modify the project's source code.

### 9. Audit trail with key attribution (REQ-S-004)

Every audit log entry includes `key_id` (first 12 characters of the `kr-` key).
In OAuth passthrough mode, `key_id` is set to `"oauth-passthrough"` instead.
Allows correlating an event to a specific developer and revoking the key in case
of an incident.

### 10. OAuth passthrough mode (REQ-S-010)

When `oauth_passthrough: true` is set in `config.yaml`, the gateway accepts
Anthropic OAuth tokens (`sk-ant-` prefix) directly, runs the full filter pipeline,
and forwards the request with the original token unchanged.

**Tradeoff:** the dual-key bypass-prevention guarantee does not apply. A developer
who knows the gateway URL can call Anthropic directly by unsetting `ANTHROPIC_BASE_URL`.
The filter pipeline protects against accidental exfiltration but not against deliberate bypass.

**Default:** `oauth_passthrough: false` — OAuth tokens are rejected with HTTP 401.

See [REQ-S-010](../requirements/security.md) and [US-16](../user-stories/US-16-oauth-support.md).

---

## Known and accepted vulnerabilities

### config.yaml is trusted input

`.kiri/config.yaml` is committed to git and read by the container at startup.
The values `ollama_base_url` and `openai_upstream_url` control where the gateway
sends traffic. An attacker with write access to the repository can redirect
traffic to a controlled server.

**Mitigation:** limit write access to the repository to trusted developers only.
**Not mitigated in v1:** domain validation in config.yaml.

### Fail-open on internal errors

If ChromaDB or Ollama fail, the gateway does PASS.
An attacker who manages to corrupt the vector DB reduces the gateway to L2 only.

**Mitigation:** L2 remains always active (symbol matching in memory).
**Monitoring:** L1/L3 errors are logged in the audit log.

### Host filesystem

`.kiri/upstream.key` is on the host filesystem. A user with filesystem access
can read it (permissions 600 restrict other users on the same OS, not attackers
with physical access or root).

**Accepted mitigation:** in environments with a secrets manager (Vault, etc.), use it instead of the file.

---

## Security audit — resolved findings (session 2026-04-19)

| Finding | Severity | Resolved in |
|---------|----------|-----------|
| Gateway was binding on 0.0.0.0 — exposed on the LAN | High | commit `3829b49` |
| Upstream key in env var — visible via docker inspect | High | commit `c81d85b` |
| secrets/symbols/summaries files written without chmod | Medium | commit `24ef5f8` |
| Gateway keys without expiry | Medium | commit `24ef5f8` |
| Key attribution absent from audit log | Medium | commit `b404bdb` |
| Content-type bypass (tool_result blocks) | High | commit `864fd1f` |
| No body size limit | Medium | commit `864fd1f` |
| Sensitive prompt in shell history (inspect) | Low | commit `07619d6` |
