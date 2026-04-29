# ADR-003: Upstream Anthropic key via Docker secret (not env var)

## Status
Accepted

## Context

The gateway must hold the real Anthropic key (`sk-ant-xxx`) to forward
requests to the upstream. This key must NOT be visible to developers.

The simplest method would be to pass it as an environment variable in `docker-compose.yml`:

```yaml
environment:
  - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
```

But this exposes the key in at least three ways:
1. `docker inspect <container>` shows all environment variables in plain text
2. `docker exec <container> env` does the same
3. The environment variable is visible to any process in the container

A developer with Docker access (required to use the gateway) can see the key
and bypass the proxy by calling Anthropic directly — defeating the entire model.

## Decision

Use **Docker secrets** to mount the key as a file:

```yaml
# docker-compose.yml
services:
  gateway:
    secrets:
      - anthropic_key

secrets:
  anthropic_key:
    file: .kiri/upstream.key
```

The file is mounted at `/run/secrets/anthropic_key` inside the container.
It does not appear in `docker inspect`, `docker exec env`, or container logs.

`KeyManager.get_upstream_key()` reads the file:

```python
def get_upstream_key(self) -> str:
    secret_path = self._secrets_dir / "anthropic_key"
    if secret_path.exists():
        return secret_path.read_text().strip()
    return os.environ.get("ANTHROPIC_API_KEY", "")  # fallback local dev
```

The env var fallback is intentional for local development without Docker.

## Consequences

**Positive:**
- The key does not appear in `docker inspect` or `docker exec env`
- `.kiri/upstream.key` is gitignored → does not end up in git
- `chmod 600 .kiri/upstream.key` (owner-read only) — file not readable by other users
- Env var fallback maintains DX for local development without Docker

**Negative:**
- `.kiri/upstream.key` is a file on the host filesystem → anyone with filesystem access
  can read it (e.g. other users on the system, malware)
  → mitigation: chmod 600, owner-only directory
- Does not replace a secrets manager (Vault, AWS Secrets Manager)
  → sufficient for single-developer on-premises use

**Derived constraint:**
- The Docker volume must mount `.kiri/` in read-write (not read-only like the workspace)
  to allow writing the audit log and index

## Alternatives considered

**Environment variable in docker-compose.yml:**
- Exposed via `docker inspect` — eliminated for the main reason above

**Docker build argument (ARG):**
- The key ends up in the image layer → visible via `docker history`

**Separate encrypted volume:**
- Complexity >> benefit for v1

**HashiCorp Vault / AWS Secrets Manager:**
- Correct for environments with an existing secrets manager infrastructure
- Setup complexity disproportionate for single-developer local use
