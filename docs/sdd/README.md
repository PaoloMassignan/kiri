# Software Design Document

This SDD describes the internal design of Kiri.

## Sections

| File | Contents |
|------|----------|
| [`01-overview.md`](01-overview.md) | System purpose, scope, and key design principles |
| [`02-architecture.md`](02-architecture.md) | Component architecture, deployment model, data flow |
| [`03-filter-pipeline.md`](03-filter-pipeline.md) | L1/L2/L3 filter pipeline — thresholds, grace zone, REDACT logic |
| [`04-data-model.md`](04-data-model.md) | Data structures: AuditEntry, KeyInfo, SecretsStore format |
| [`05-api.md`](05-api.md) | HTTP API: proxy endpoints, CLI commands, error codes |
| [`06-security.md`](06-security.md) | Threat model, key handling, audit trail, Docker isolation |

## Relationship to requirements

Every design decision in this document should trace back to a requirement in [`../requirements/`](../requirements/) or an ADR in [`../adr/`](../adr/). If a design choice has no requirement driving it, it should be questioned.
