#!/usr/bin/env bash
# E2E test runner for Kiri.
#
# Simulates a developer installing Kiri on a clean machine, protecting a real
# open-source project, and verifying that LLM requests are correctly redacted.
#
# Usage:
#   bash tests/e2e/run.sh [--suite easy|full]
#
# Environment variables honoured:
#   MOCK_PORT          port for the mock LLM server (default: 9999)
#   KIRI_PORT          port Kiri listens on (default: 8765)
#   E2E_ANTHROPIC_KEY  fake Anthropic key passed to installer (default: sk-ant-e2e-test-key)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
KIRI_DIR="$REPO_ROOT/kiri"
FIXTURES_DIR="$REPO_ROOT/benchmarks/real-projects/fixtures"
ARTIFACTS_DIR="$REPO_ROOT/artifacts"

SUITE="easy"
MOCK_PORT="${MOCK_PORT:-9999}"
KIRI_PORT="${KIRI_PORT:-8765}"
FAKE_KEY="${E2E_ANTHROPIC_KEY:-sk-ant-e2e-test-key}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --suite) SUITE="$2"; shift 2 ;;
        *) printf "Unknown argument: %s\n" "$1" >&2; exit 1 ;;
    esac
done

# ── Workspace ────────────────────────────────────────────────────────────────

E2E_WORKSPACE="$(mktemp -d)"
MOCK_PAYLOAD_DIR="$E2E_WORKSPACE/mock-payloads"
mkdir -p "$E2E_WORKSPACE/.kiri" "$MOCK_PAYLOAD_DIR"

cleanup() {
    collect_artifacts
    # Stop mock LLM
    if [[ -n "${MOCK_PID:-}" ]] && kill -0 "$MOCK_PID" 2>/dev/null; then
        kill "$MOCK_PID" 2>/dev/null || true
    fi
    # Stop Docker stack
    docker compose --project-directory "$KIRI_DIR" down --remove-orphans 2>/dev/null || true
    rm -rf "$E2E_WORKSPACE"
}

collect_artifacts() {
    mkdir -p "$ARTIFACTS_DIR/payloads" "$ARTIFACTS_DIR/config"

    docker compose --project-directory "$KIRI_DIR" logs kiri     > "$ARTIFACTS_DIR/kiri.log"     2>&1 || true
    docker compose --project-directory "$KIRI_DIR" ps            > "$ARTIFACTS_DIR/docker_ps.txt" 2>&1 || true

    [[ -f "$E2E_WORKSPACE/mock_llm.log" ]] && cp "$E2E_WORKSPACE/mock_llm.log" "$ARTIFACTS_DIR/mock_llm.log" || true

    cp -r "$MOCK_PAYLOAD_DIR"/. "$ARTIFACTS_DIR/payloads/" 2>/dev/null || true
    [[ -f "$E2E_WORKSPACE/.kiri/secrets"     ]] && cp "$E2E_WORKSPACE/.kiri/secrets"     "$ARTIFACTS_DIR/config/" || true
    [[ -f "$E2E_WORKSPACE/.kiri/config.yaml" ]] && cp "$E2E_WORKSPACE/.kiri/config.yaml" "$ARTIFACTS_DIR/config/" || true
    [[ -f "$E2E_WORKSPACE/.kiri/audit.log"   ]] && cp "$E2E_WORKSPACE/.kiri/audit.log"   "$ARTIFACTS_DIR/"        || true
}

trap cleanup EXIT

# ── Dependencies ─────────────────────────────────────────────────────────────

pip install --quiet fastapi uvicorn pyyaml 2>&1 | tail -3

# ── Mock LLM ─────────────────────────────────────────────────────────────────

printf "\n[e2e] Starting mock LLM on port %s...\n" "$MOCK_PORT"
MOCK_PAYLOAD_DIR="$MOCK_PAYLOAD_DIR" MOCK_PORT="$MOCK_PORT" \
    python3 "$SCRIPT_DIR/mock_llm.py" > "$E2E_WORKSPACE/mock_llm.log" 2>&1 &
MOCK_PID=$!

for i in $(seq 1 15); do
    if curl -sf "http://localhost:$MOCK_PORT/health" >/dev/null 2>&1; then
        printf "[e2e] Mock LLM ready.\n"
        break
    fi
    sleep 1
    if [[ $i -eq 15 ]]; then
        printf "[e2e] ERROR: mock LLM did not start within 15s\n" >&2
        exit 1
    fi
done

# ── Docker Compose override ──────────────────────────────────────────────────
# Tell Compose to use both the base file and the E2E override.
# Must be absolute paths so they resolve regardless of --project-directory.
export COMPOSE_FILE="$KIRI_DIR/docker-compose.yml:$SCRIPT_DIR/docker-compose.e2e.yml"

# Workspace volumes
export WORKSPACE_HOST="$E2E_WORKSPACE"
export KIRI_STATE_HOST="$E2E_WORKSPACE/.kiri"

# ── Installer ────────────────────────────────────────────────────────────────

printf "\n[e2e] Running installer (--ci)...\n"
bash "$REPO_ROOT/install/linux/install.sh" --ci --anthropic-key "$FAKE_KEY"

# ── Kiri key ─────────────────────────────────────────────────────────────────

printf "\n[e2e] Creating Kiri developer key...\n"
KIRI_KEY=$(docker compose --project-directory "$KIRI_DIR" exec -T kiri kiri key create 2>&1 | tail -1 | tr -d '[:space:]')
if [[ "$KIRI_KEY" != kr-* ]]; then
    printf "[e2e] ERROR: key creation failed, got: %s\n" "$KIRI_KEY" >&2
    exit 1
fi
printf "[e2e] Key: %s\n" "$KIRI_KEY"

# ── Proxy health ─────────────────────────────────────────────────────────────

printf "\n[e2e] Verifying proxy responds on :%s...\n" "$KIRI_PORT"
if ! curl -sf "http://localhost:$KIRI_PORT/health" >/dev/null 2>&1; then
    printf "[e2e] ERROR: proxy is not healthy\n" >&2
    exit 1
fi
printf "[e2e] Proxy healthy.\n"

# ── Scenarios ────────────────────────────────────────────────────────────────

printf "\n[e2e] Running scenarios (suite=%s)...\n\n" "$SUITE"
python3 "$SCRIPT_DIR/run_scenarios.py" \
    --scenarios "$SCRIPT_DIR/scenarios.yaml" \
    --fixtures-dir "$FIXTURES_DIR" \
    --workspace "$E2E_WORKSPACE" \
    --kiri-url "http://localhost:$KIRI_PORT" \
    --kiri-key "$KIRI_KEY" \
    --mock-payload-dir "$MOCK_PAYLOAD_DIR" \
    --kiri-dir "$KIRI_DIR" \
    --suite "$SUITE"
