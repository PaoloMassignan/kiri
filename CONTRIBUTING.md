# Contributing to Kiri

Thank you for your interest in contributing. This document covers how to set up the development environment, run tests, and submit changes.

## Development setup

```bash
git clone https://github.com/PaoloMassignan/kiri.git kiri
cd kiri
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
bash scripts/install-hooks.sh   # installs pre-commit hook
```

## Running the tests

```bash
cd kiri
python -m pytest tests/unit/ -q          # unit tests (fast, no external deps)
python -m pytest tests/security/ -q      # security scenarios
```

Integration tests require `kiri/example_projects/` — see `kiri/example_projects/README.md`.

## Code style

- Formatter/linter: **ruff** (`ruff check src/ tests/`)
- Type checker: **mypy** (`mypy src/`)
- Line length: 100
- Python 3.11+

CI runs both automatically on every pull request.

## Submitting a pull request

1. Fork the repository and create a branch from `main`
2. Make your changes — keep commits focused and descriptive
3. Ensure `pytest tests/unit/` passes and `ruff check` is clean
4. Open a pull request with a clear description of what and why

## Critical invariants — read before changing the filter pipeline

These must not be changed without updating the relevant ADR:

- **Fail-open on L1/L3 errors** — errors produce `PASS`, not `BLOCK` (see ADR-004)
- **L2 always active** — symbol matching never fails silently
- **Bind to 127.0.0.1** — `kiri serve` must never bind to `0.0.0.0`
- **No source code in cloud** — the indexer stores float vectors only, never source text

See [`DECISIONS.md`](DECISIONS.md) and [`docs/adr/`](docs/adr/) for the rationale behind each decision.

## Reporting security vulnerabilities

See [`SECURITY.md`](SECURITY.md) — please do not open a public issue for security bugs.
