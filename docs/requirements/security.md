# Security Requirements — EARS Format

Requirements ID prefix: `REQ-S-`

See [`README.md`](README.md) for EARS template reference.
See [`../sdd/06-security.md`](../sdd/06-security.md) for the full threat model.

---

## REQ-S-001: Gateway key authentication

```
WHEN the gateway receives a request,
the gateway SHALL reject the request with HTTP 401
if the Authorization header does not contain a valid, non-expired kr- key.

The gateway SHALL NOT accept Anthropic sk-ant- keys directly from clients
UNLESS oauth_passthrough is set to true in config.yaml (see REQ-S-010).
```

**ADR:** [ADR-005](../adr/ADR-005-gateway-key-model.md)
**Tests:** `tests/unit/test_key_manager.py`, `tests/unit/test_server.py`

---

## REQ-S-010: OAuth passthrough mode

```
WHEN oauth_passthrough is false (default),
the gateway SHALL reject requests carrying an Anthropic sk-ant- token with HTTP 401.

WHEN oauth_passthrough is true,
the gateway SHALL accept requests carrying an Anthropic sk-ant- token,
apply the full filter pipeline (L1/L2/L3),
and forward the request to upstream using the original token unchanged.

WHEN oauth_passthrough is true and the filter pipeline returns BLOCK,
the gateway SHALL return the standard block response (HTTP 200 with permission_error body).

WHEN oauth_passthrough is true,
the gateway SHALL record key_id = "oauth-passthrough" in the audit log.

The gateway SHALL continue to validate kr- keys normally regardless of oauth_passthrough.
```

**Rationale:** enables developers using Claude Pro/Max (OAuth, no static API key) to
benefit from Kiri's filter pipeline. Bypass-prevention (dual-key model) does not apply
in this mode — the developer holds the real upstream credential.
**User story:** US-16
**Tests:** `tests/unit/test_server.py`, `tests/unit/test_key_manager.py`

---

## REQ-S-002: Upstream key isolation

```
The gateway SHALL read the upstream Anthropic API key from
/run/secrets/anthropic_key (Docker secret file) at startup.

The gateway SHALL NOT expose the upstream API key via environment variables,
docker inspect output, or any HTTP response.

IF /run/secrets/anthropic_key does not exist,
THEN the gateway SHALL fall back to the ANTHROPIC_API_KEY environment variable
(local development only — must not be used in production).
```

**ADR:** [ADR-003](../adr/ADR-003-docker-secrets.md)
**Tests:** `tests/unit/test_key_manager.py`

---

## REQ-S-003: Gateway key expiry

```
WHEN a kr- key is created with --expires-in <days>,
the gateway SHALL store the expiry date in key metadata.

WHEN the gateway receives a request with a kr- key that is past its expiry date,
the gateway SHALL reject the request with HTTP 401.

WHEN a developer runs "kiri key list",
the gateway SHALL display the expiry date for each key.
```

**Tests:** `tests/unit/test_key_manager.py`, `tests/unit/test_cli_key.py`

---

## REQ-S-004: Per-key attribution in the audit log

```
WHEN the kiri logs an audit entry,
the gateway SHALL include the key_id field
containing the first 12 characters of the kr- key used for the request.
```

**Rationale:** enables per-developer audit trail and targeted key revocation.
**Tests:** `tests/unit/test_audit_log.py`

---

## REQ-S-005: Localhost binding

```
The gateway SHALL bind the proxy server to 127.0.0.1 only.
The gateway SHALL NOT bind to 0.0.0.0 or any interface reachable from the LAN.
```

**Rationale:** prevents other machines on the same network from using the gateway.
**Tests:** `tests/unit/test_cli_app.py::test_serve_binds_to_localhost`

---

## REQ-S-006: Pre-commit hook (key exposure prevention)

```
The gateway SHALL provide a pre-commit hook that scans staged diff lines
for the pattern kr-[A-Za-z0-9_-]{20,}.

IF a staged change contains a kr- key,
THEN the hook SHALL block the commit with an error message.
```

**Rationale:** prevents accidental commit of kiri keys to git history.
**Scripts:** `scripts/hooks/pre-commit`, `scripts/install-hooks.sh`

---

## REQ-S-007: Permissions on sensitive files

```
WHEN the gateway writes .kiri/secrets, symbols.json, or summaries.json,
the gateway SHALL set file permissions to 0o600 (owner read/write only)
on POSIX systems.
```

**Rationale:** prevents other users on the same system from reading the secret registry.
**Tests:** `tests/unit/test_secrets_store.py::test_atomic_write_produces_owner_only_file`

---

## REQ-S-008: Body size limit

```
WHEN the gateway receives a request with Content-Length exceeding 10 MB,
the gateway SHALL return HTTP 413 before processing authentication or filtering.
```

**Rationale:** prevents resource exhaustion via oversized requests.
**Tests:** `tests/unit/test_server.py`

---

## REQ-S-009: Path traversal protection

```
WHEN a developer runs "kiri add <path>",
IF the resolved absolute path is outside the workspace root,
THEN the gateway SHALL reject the command with an error.

WHEN a developer runs "kiri add <glob>",
IF the glob pattern expands to any path outside the workspace root,
THEN those paths SHALL be silently excluded from the result.
```

**Rationale:** prevents protecting files outside the project to avoid information leakage
about the surrounding filesystem. Glob expansion goes through `SecretsStore._validate_path`
which calls `path.is_relative_to(workspace)`.
**Tests:** `tests/security/test_path_traversal.py`
