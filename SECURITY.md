# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| latest (`main`) | ✅ |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities by opening a **private GitHub security advisory**
([github.com/…/security/advisories/new](../../security/advisories/new))
with the title: `[KIRI SECURITY] <short description>`

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix (optional)

You will receive an acknowledgement within **48 hours** and a resolution timeline within **7 days**.

Once the fix is released, you will be credited in the changelog unless you prefer to remain anonymous.

## Scope

The following are in scope:

- Authentication bypass (kiri key validation)
- Prompt injection that bypasses the filter pipeline
- Path traversal in file indexing
- Information disclosure (source code leaking despite REDACT decision)
- Denial of service via crafted payloads

The following are out of scope:

- Vulnerabilities in Ollama, ChromaDB, or other upstream dependencies
  (report these to their respective maintainers)
- Issues that require physical access to the host machine
- Social engineering

## Security model

Kiri is an on-premises tool. Its threat model assumes:

- The host machine is trusted
- The Docker network is isolated
- Developers using `kr-` keys are authenticated employees

See [`docs/sdd/06-security.md`](docs/sdd/06-security.md) for the full threat model.
