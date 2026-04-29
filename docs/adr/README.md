# Architecture Decision Records

ADRs document *why* key design decisions were made — not just what was decided, but what context forced the choice and what alternatives were rejected.

## Why ADRs matter for AI-assisted development

When an AI tool (or a new developer) reads this codebase, it sees *what* the code does but not *why*. ADRs prevent well-intentioned "improvements" that would silently break a design invariant.

Example: ADR-004 documents that the gateway is fail-open by design. Without it, an AI might reasonably suggest making it fail-closed "for security" — which would be wrong.

## Template

```markdown
# ADR-NNN: Title

## Status
Accepted | Deprecated | Superseded by ADR-NNN

## Context
What situation forced a decision? What constraints existed?

## Decision
What was decided?

## Consequences
What becomes easier? What becomes harder? What is now a known limitation?

## Alternatives considered
What else was evaluated and why was it rejected?
```

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](ADR-001-filter-3-levels.md) | Three-level filter pipeline | Accepted |
| [ADR-002](ADR-002-chromadb-embedded.md) | ChromaDB embedded (no server) | Accepted |
| [ADR-003](ADR-003-docker-secrets.md) | Docker secrets for upstream API key | Accepted |
| [ADR-004](ADR-004-fail-open.md) | Fail-open on L1/L3 errors | Accepted |
| [ADR-005](ADR-005-gateway-key-model.md) | Two-key model (kr- keys vs sk-ant- secret) | Accepted |
| [ADR-006](ADR-006-redact-vs-block.md) | REDACT decision in grace zone | Accepted |
| [ADR-007](ADR-007-ears-requirements.md) | EARS format for requirements | Accepted |
| [ADR-008](ADR-008-redact-as-default.md) | REDACT as default — BLOCK only on explicit malicious intent | Accepted |
