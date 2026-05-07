# Kiri — Project Context (OpenCode / AGENTS.md)

**Kiri** is an open-source on-premises proxy that intercepts LLM calls (Claude Code,
OpenCode, Cursor, Copilot) and prevents proprietary source code from leaving the network.

## Repository Layout

```
AI-Layer/   ← Kiri repository
├── AGENTS.md          ← you are here — project-level AI context (OpenCode)
├── CLAUDE.md          ← same content for Claude Code
├── DECISIONS.md       ← key design decisions at a glance (read this first)
├── README.md          ← navigation for humans
│
├── kiri/            ← production implementation (FastAPI proxy + filter pipeline)
│   ├── AGENTS.md      ← gateway management commands for OpenCode
│   ├── CLAUDE.md      ← same commands for Claude Code
│   ├── src/           ← source code
│   └── tests/         ← 600+ passing tests
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

## How to Navigate This Project

1. **New to the project?** Read `DECISIONS.md` (2 min) then `docs/sdd/01-overview.md`
2. **Working on the filter pipeline?** Read `docs/adr/ADR-001` + `docs/sdd/03-filter-pipeline.md`
3. **Working on security?** Read `docs/sdd/06-security.md` (threat model and audit log of known findings)
4. **Managing the gateway?** See `kiri/AGENTS.md` for CLI commands

## Critical Invariants — Do Not Change Without Reading the ADR

- **Fail-open on L1/L3 errors** (ADR-004): errors → PASS, not BLOCK. By design.
- **L2 always active**: symbol matching never fails silently — it is the safety net when L1/L3 are degraded.
- **Bind to 127.0.0.1**: `kiri serve` must never bind to 0.0.0.0 (REQ-S-005).
- **No code in cloud**: the indexer stores float vectors only, never source text (REQ-NF-005).

## Working in This Repo

- All code is in `kiri/` — run tests with `cd kiri && python -m pytest tests/unit/ -q`
- `kiri/example_projects/` is **not in git** — security/integration tests skip gracefully if missing (3 skipped is normal). See `kiri/example_projects/README.md` to populate.
- Requirements are in `docs/requirements/` in EARS format — each has an ID (REQ-F-NNN)
- Every non-obvious decision has an ADR in `docs/adr/` — read it before "fixing" something
