# Kiri — Project Context

**Kiri** is an open-source on-premises proxy that intercepts LLM calls (Claude Code,
Cursor, Copilot) and prevents proprietary source code from leaving the network.

## Repository layout

```
AI-Layer/   ← Kiri repository
├── CLAUDE.md          ← you are here — project-level AI context
├── DECISIONS.md       ← key design decisions at a glance (read this first)
├── README.md          ← navigation for humans
│
├── kiri/            ← production implementation (FastAPI proxy + filter pipeline)
│   ├── CLAUDE.md      ← gateway management commands (kiri add/rm/status/inspect)
│   ├── src/           ← source code
│   └── tests/         ← 593 passing tests
│
├── docs/
│   ├── requirements/  ← EARS-formatted requirements (REQ-F, REQ-S, REQ-NF)
│   ├── adr/           ← Architecture Decision Records (why, not what)
│   ├── sdd/           ← Software Design Document (01-overview through 06-security)
│   ├── diagrams/      ← sequence and integration diagrams
│   ├── user-stories/  ← US-01 through US-16
│   └── guides/        ← coding rules, technology stack, project structure
│
└── benchmarks/        ← evaluation datasets and runners
```

## How to navigate this project

1. **New to the project?** Read `DECISIONS.md` (2 min) then `docs/sdd/01-overview.md`
2. **Working on the filter pipeline?** Read `docs/adr/ADR-001` + `docs/sdd/03-filter-pipeline.md`
3. **Working on security?** Read `docs/sdd/06-security.md` (includes threat model and audit log of known findings)
4. **Managing the gateway?** See `kiri/CLAUDE.md` for CLI commands

## Critical invariants — do not change without reading the ADR

- **Fail-open on L1/L3 errors** (ADR-004): errors → PASS, not BLOCK. By design.
- **L2 always active**: symbol matching never fails silently — it is the safety net when L1/L3 are degraded.
- **Bind to 127.0.0.1**: `kiri serve` must never bind to 0.0.0.0 (REQ-S-005).
- **No code in cloud**: the indexer stores float vectors only, never source text (REQ-NF-005).

## Working in this repo

- All code is in `kiri/` — run tests with `cd kiri && python -m pytest tests/unit/ -q`
- `kiri/example_projects/` is **not in git** — security/integration tests skip gracefully if missing (3 skipped is normal). See `kiri/example_projects/README.md` to populate.
- Requirements are in `docs/requirements/` in EARS format — each has an ID (REQ-F-NNN)
- Every non-obvious decision has an ADR in `docs/adr/` — read it before "fixing" something
