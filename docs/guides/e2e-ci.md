# E2E CI — Installation and Integration Tests

## Purpose

The unit test suite (593 tests) verifies individual components in isolation.
This document specifies a complementary **end-to-end black-box layer** that
verifies Kiri works correctly from a developer's perspective: install, protect,
send, assert.

The goals are:

- Catch regressions that unit tests cannot see: broken Docker wiring, installer
  bugs, filter pipeline failures under the real proxy.
- Simulate a real developer workflow with real open-source code — not synthetic
  fixtures.
- Keep the test cheap: no real API keys, no external calls, no ML inference
  required for the core redaction cases (L2 is always active and requires
  nothing beyond the proxy itself).
- Make failures debuggable: every failed run uploads a complete artifact bundle.
- Make scenarios easy to add: one YAML entry per scenario, no code changes.

---

## Design decisions

### Reuse benchmark fixtures, do not create new ones

The `benchmarks/real-projects/fixtures/` directory already contains source
code from 10 pinned open-source projects across 7 languages. Each fixture
records the project, version, commit hash, protected symbols, source files,
and a set of test cases with expected actions.

The E2E test reuses the `cases` entries (easy tier, `expected_action: REDACT`)
from these fixtures. This means:

- The source code is already reviewed and versioned.
- The expected symbols are known in advance, so assertions are exact.
- Adding a new language means adding a fixture to `benchmarks/` (already done
  for most languages) — the E2E runner picks it up automatically.

Hard cases (`hard_cases`) require L1 (ChromaDB + embedder) or L3 (Ollama).
These are excluded from the default PR run and reserved for the nightly matrix,
where the full ML stack is available.

### Mock LLM — minimal recorder

A real Anthropic or OpenAI API key is never used. Instead, a minimal HTTP
server (see `tests/e2e/mock_llm.py`) listens on a local port and:

1. Accepts any POST to `/v1/messages` (Anthropic) or `/v1/chat/completions`
   (OpenAI-compat).
2. Writes the full request body as JSON to a file on disk.
3. Returns a fixed response: `"Mock response: safe refactor suggestion."`
4. Returns HTTP 200 and a valid API response envelope so Kiri forwards it
   without error.

The mock never inspects request content — it is a pure recorder. Assertions
are made by the test runner after the fact, reading the saved payload from
disk.

### L2-only by default

The PR workflow does not start Ollama or ChromaDB. L2 (symbol match) is
always active and catches all `expected_action: REDACT` easy-tier cases.
This means:

- The PR run takes under 3 minutes on a fresh GitHub Actions runner.
- No GPU, no large model download, no Ollama startup delay.
- The full stack (L1 + L3) runs only in the nightly workflow.

### Non-interactive installer

`install/linux/install.sh` already accepts `--anthropic-key` as a CLI flag.
The CI passes `--anthropic-key kr-e2e-test-key` (a syntactically valid fake
key) to satisfy the installer without prompting. Kiri stores this as the
upstream key inside the container; the mock LLM intercepts all outbound
requests so the fake key is never actually presented to Anthropic.

The upstream URL (where Kiri forwards requests) is overridden via
`KIRI_UPSTREAM_URL` environment variable in `docker-compose.yml`, pointing
at the mock LLM container rather than `api.anthropic.com`.

---

## File structure

```
tests/e2e/
├── mock_llm.py              # minimal FastAPI recorder server
├── scenarios.yaml           # test scenarios (references fixture entries)
└── run.sh                   # orchestration script

.github/workflows/
├── ci.yml                   # existing unit test workflow (unchanged)
└── e2e.yml                  # new E2E workflow (PR + nightly)
```

---

## mock_llm.py

A single-file FastAPI app. Requirements: `fastapi`, `uvicorn` (both already
in `kiri/pyproject.toml` dev dependencies).

**Endpoints:**

| Method | Path | Behaviour |
|--------|------|-----------|
| POST | `/v1/messages` | Save body → `$MOCK_PAYLOAD_DIR/request_{n}.json`, return fixed Anthropic response |
| POST | `/v1/chat/completions` | Save body → same dir, return fixed OpenAI response |
| GET | `/health` | Return `{"status": "ok"}` |

**Fixed Anthropic response envelope:**
```json
{
  "id": "msg_mock",
  "type": "message",
  "role": "assistant",
  "content": [{"type": "text", "text": "Mock response: safe refactor suggestion."}],
  "model": "claude-sonnet-4-6",
  "stop_reason": "end_turn",
  "usage": {"input_tokens": 10, "output_tokens": 8}
}
```

**Fixed OpenAI response envelope:**
```json
{
  "id": "chatcmpl-mock",
  "object": "chat.completion",
  "choices": [{"index": 0, "message": {"role": "assistant",
    "content": "Mock response: safe refactor suggestion."}, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18}
}
```

`MOCK_PAYLOAD_DIR` defaults to `/tmp/mock_llm_payloads`. The runner mounts
this directory as a Docker volume so payloads are accessible from the host
after the test.

---

## scenarios.yaml

Each entry maps to one entry in a `benchmarks/real-projects/fixtures/`
fixture file. The runner loads the fixture, extracts the prompt, sends it
through Kiri, and checks the assertions.

```yaml
scenarios:

  - id: e2e-flask-001
    fixture: flask        # loads benchmarks/real-projects/fixtures/flask/fixture.yaml
    case: flask-001       # must match an entry in fixture.cases[].id
    description: "Flask class body must be redacted — L2 symbol match"
    assertions:
      decision: REDACT
      must_not_contain:        # strings that must NOT appear in the forwarded payload
        - "make_config"
        - "make_response"
        - "wsgi_app"
      must_contain_stub: true  # payload must contain "[PROTECTED" or "# [protected"

  - id: e2e-flask-pass-001
    fixture: flask
    case: flask-004
    description: "CLI question with no protected symbols must pass unmodified"
    assertions:
      decision: PASS
      must_not_contain: []
      must_contain_stub: false

  - id: e2e-requests-001
    fixture: requests
    case: requests-001
    description: "requests Session body must be redacted"
    assertions:
      decision: REDACT
      must_not_contain: ["send", "resolve_redirects", "rebuild_auth"]
      must_contain_stub: true

  - id: e2e-express-001
    fixture: express
    case: express-001
    description: "Express Router body must be redacted (JS/brace-language)"
    assertions:
      decision: REDACT
      must_not_contain: ["layer.match", "paramcalled"]
      must_contain_stub: true

  - id: e2e-nestjs-001
    fixture: nestjs
    case: nestjs-001
    description: "NestJS DependenciesScanner body must be redacted (TS)"
    assertions:
      decision: REDACT
      must_not_contain: ["scanForModules", "insertImports"]
      must_contain_stub: true
```

To add a new scenario: add one entry pointing at an existing fixture case.
No code changes required.

---

## run.sh

The script is the single source of truth for the E2E test execution. The
GitHub Action calls it directly; a developer can also run it locally.

**Arguments:**
```
run.sh [--suite easy|full] [--project-dir PATH]
```

- `--suite easy` (default): L2 only, no Ollama/ChromaDB.
- `--suite full`: full pipeline; requires Ollama with `qwen2.5:3b` pulled.
- `--project-dir`: path to a directory that simulates a developer's workspace
  (defaults to a temp dir).

**Steps executed:**

```
1.  Create temp workspace directory
2.  Run installer:  ./install/linux/install.sh --anthropic-key kr-e2e-test-key
3.  Wait for Kiri proxy to respond on :8765  (timeout: 30s)
4.  For each scenario in scenarios.yaml:
    a.  Load fixture source files
    b.  Write source files to workspace
    c.  Run: kiri add <source_file>
    d.  Wait for indexing to complete (kiri status shows chunk count > 0)
    e.  Build Anthropic-format request body from scenario prompt
    f.  POST to http://localhost:8765/v1/messages  with Authorization: Bearer kr-e2e-test-key
    g.  Assert HTTP response code (PASS → 200, REDACT → 200, BLOCK → 403)
    h.  Read mock payload saved by mock_llm
    i.  Assert must_not_contain strings absent from payload text
    j.  Assert stub marker present/absent per scenario
    k.  Print PASS / FAIL with diff on failure
5.  On any failure: collect artifacts (see below) and exit 1
6.  Print summary table and exit 0
```

**Artifact collection** (always runs, even on success — upload only on failure
in CI):

```
artifacts/
├── kiri.log              # docker compose logs kiri
├── mock_llm.log          # mock server stdout/stderr
├── docker_ps.txt         # docker compose ps
├── payloads/
│   ├── request_1.json    # original request sent to Kiri (saved by run.sh before POST)
│   └── forwarded_1.json  # payload received by mock LLM
└── config/
    ├── .kiri/secrets
    └── .kiri/config.yaml
```

---

## GitHub Actions workflows

### e2e.yml — PR and nightly

```yaml
name: E2E

on:
  push:
    branches: [main]
    paths:
      - "kiri/**"
      - "install/**"
      - "tests/e2e/**"
      - ".github/workflows/e2e.yml"
  pull_request:
    paths:
      - "kiri/**"
      - "install/**"
      - "tests/e2e/**"
      - ".github/workflows/e2e.yml"
  schedule:
    - cron: "0 3 * * *"   # nightly at 03:00 UTC
  workflow_dispatch:
    inputs:
      suite:
        description: "Test suite"
        required: false
        default: "easy"
        type: choice
        options: [easy, full]

jobs:

  # ── PR / push: Linux only, L2 suite ─────────────────────────────────────
  e2e-fast:
    if: github.event_name != 'schedule'
    name: E2E fast (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-24.04]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python (mock LLM)
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install mock LLM dependencies
        run: pip install fastapi uvicorn

      - name: Start mock LLM
        run: |
          python tests/e2e/mock_llm.py &
          echo $! > /tmp/mock_llm.pid
          # wait for it to be ready
          for i in $(seq 1 10); do
            curl -sf http://localhost:9999/health && break || sleep 1
          done

      - name: Run E2E suite
        run: bash tests/e2e/run.sh --suite easy
        env:
          KIRI_UPSTREAM_URL: http://localhost:9999

      - name: Upload artifacts on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-artifacts-${{ matrix.os }}-${{ github.run_id }}
          path: artifacts/
          retention-days: 7

  # ── Nightly: multi-platform, full suite ──────────────────────────────────
  e2e-nightly:
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    name: E2E nightly (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-24.04, macos-15, windows-2025]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python (mock LLM)
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install mock LLM dependencies
        run: pip install fastapi uvicorn

      - name: Start mock LLM
        shell: bash
        run: |
          python tests/e2e/mock_llm.py &
          for i in $(seq 1 15); do
            curl -sf http://localhost:9999/health && break || sleep 1
          done

      - name: Run E2E suite (full)
        shell: bash
        run: bash tests/e2e/run.sh --suite ${{ inputs.suite || 'full' }}
        env:
          KIRI_UPSTREAM_URL: http://localhost:9999

      - name: Upload artifacts on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-nightly-${{ matrix.os }}-${{ github.run_id }}
          path: artifacts/
          retention-days: 14
```

---

## How to add a new scenario

1. Confirm the target project has a fixture in
   `benchmarks/real-projects/fixtures/<project>/fixture.yaml`.
2. Pick a case ID from the `cases` list (easy tier) or `hard_cases` (full
   suite only).
3. Add one entry to `tests/e2e/scenarios.yaml` with the assertions that match
   the expected behaviour.
4. Open a PR — the E2E job runs automatically.

No Python, no shell changes required.

---

## How to run locally

```bash
# Start the mock LLM in one terminal
pip install fastapi uvicorn
python tests/e2e/mock_llm.py

# Run the fast suite in another terminal
KIRI_UPSTREAM_URL=http://localhost:9999 bash tests/e2e/run.sh --suite easy

# Inspect the artifacts on failure
ls artifacts/
cat artifacts/payloads/forwarded_1.json | python -m json.tool
```

---

## Relationship to other test layers

| Layer | What it tests | Where |
|-------|---------------|-------|
| Unit tests | Individual Python components | `kiri/tests/unit/` |
| Security tests | Injection, bypass attempts | `kiri/tests/security/` |
| Benchmark | Detection quality (F1, FP, FN) | `benchmarks/` |
| **E2E (this doc)** | Full install + proxy + redaction | `tests/e2e/` |

The E2E layer is intentionally not a substitute for the benchmark — it checks
that the system works end-to-end, not that the detection quality meets a
threshold. Benchmark runs remain a separate manual + nightly concern.
