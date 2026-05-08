#!/usr/bin/env bash
# Kiri Gateway -- Linux installer
#
# Usage:
#   ./install.sh
#   ./install.sh --anthropic-key sk-ant-xxx
#   ./install.sh --anthropic-key sk-ant-xxx --openai-key sk-xxx
#
# Requires: Docker Engine with Compose plugin (v2)
# Autostart: systemd user service (falls back to shell profile if unavailable)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
KIRI_DIR="$REPO_ROOT/kiri"
KIRI_DATA="$KIRI_DIR/.kiri"
WRAPPER_DIR="$HOME/.kiri/bin"
WRAPPER_PATH="$WRAPPER_DIR/kiri"
AUTOSTART_SCRIPT="$WRAPPER_DIR/kiri-autostart.sh"
SYSTEMD_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="kiri-gateway"
SERVICE_FILE="$SYSTEMD_DIR/$SERVICE_NAME.service"

ANTHROPIC_KEY=""
OPENAI_KEY=""
CI_MODE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --anthropic-key) ANTHROPIC_KEY="$2"; shift 2 ;;
        --openai-key)    OPENAI_KEY="$2";    shift 2 ;;
        --ci)            CI_MODE=true; shift ;;
        *) printf "Unknown argument: %s\n" "$1" >&2; exit 1 ;;
    esac
done

# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; CYAN=$'\033[0;36m'
YELLOW=$'\033[1;33m'; GRAY=$'\033[0;37m'; WHITE=$'\033[1;37m'; NC=$'\033[0m'

write_step() { printf "\n  ${CYAN}--> %s${NC}\n" "$1"; }
write_ok()   { printf "      ${GREEN}OK   %s${NC}\n" "$1"; }
write_info() { printf "      ${GRAY}...  %s${NC}\n" "$1"; }
write_warn() { printf "      ${YELLOW}WARN %s${NC}\n" "$1"; }
fail()       { printf "\n  ${RED}ERROR: %s${NC}\n\n" "$1" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

detect_profile() {
    case "${SHELL:-}" in
        */zsh)  printf "%s/.zshrc" "$HOME" ;;
        */bash) printf "%s/.bashrc" "$HOME" ;;
        *)      printf "%s/.profile" "$HOME" ;;
    esac
}

# Append a tagged block to the shell profile (idempotent) -- GNU sed
add_to_profile() {
    local profile="$1"
    local block="$2"
    local tag="kiri-gateway"

    if grep -q ">>> $tag >>>" "$profile" 2>/dev/null; then
        sed -i "/# >>> $tag >>>/,/# <<< $tag <<</d" "$profile"
    fi

    printf "\n# >>> %s >>>\n%s\n# <<< %s <<<\n" "$tag" "$block" "$tag" >> "$profile"
}

wait_for_gateway() {
    local timeout="${1:-600}"
    local start=$SECONDS
    local attempt=0
    while (( SECONDS - start < timeout )); do
        attempt=$(( attempt + 1 ))
        if curl -sf "http://localhost:8765/health" >/dev/null 2>&1; then
            return 0
        fi
        if (( attempt % 5 == 0 )); then
            write_info "still waiting... $(( SECONDS - start ))s (model download can take 5-30 min on first run)"
        fi
        sleep 3
    done
    return 1
}

# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

printf "\n  ${WHITE}Kiri Gateway - Linux Installer${NC}\n"
printf   "  ${GRAY}===============================${NC}\n\n"

# -- Step 1: Docker -----------------------------------------------------------

write_step "Checking Docker..."

if ! command -v docker &>/dev/null; then
    fail "Docker not found. Install Docker Engine: https://docs.docker.com/engine/install/"
fi
write_ok "docker CLI found ($(command -v docker))"

if ! docker ps &>/dev/null; then
    printf "\n  ${YELLOW}Tip: if Docker requires sudo, add your user to the docker group:${NC}\n"
    printf   "       sudo usermod -aG docker \$USER   (then log out and back in)\n\n"
    fail "Docker daemon is not responding. Start it with: sudo systemctl start docker"
fi
write_ok "Docker daemon is running"

if ! docker compose version &>/dev/null; then
    fail "Docker Compose plugin not found. Install it: https://docs.docker.com/compose/install/linux/"
fi
write_ok "Docker Compose plugin found"

# -- Step 2: Tool selection ---------------------------------------------------

write_step "Which tools do you want to route through Kiri?"
printf "\n"
printf "  ${WHITE}[1] Claude Code                       (sets ANTHROPIC_BASE_URL)${NC}\n"
printf "  ${WHITE}[2] Cursor / Windsurf / OpenAI tools  (sets OPENAI_BASE_URL)${NC}\n"
printf "  ${WHITE}[3] Both${NC}\n"
printf "  ${GRAY}[4] None -- I will configure my tools manually${NC}\n"
printf "\n"
if [[ "$CI_MODE" == true ]]; then
    tool_choice="4"
else
    read -rp "  Choice [1-4, default: 1]: " tool_choice
    [[ -z "$tool_choice" || ! "$tool_choice" =~ ^[1-4]$ ]] && tool_choice="1"
fi

configure_claude=false
configure_openai=false
[[ "$tool_choice" == "1" || "$tool_choice" == "3" ]] && configure_claude=true
[[ "$tool_choice" == "2" || "$tool_choice" == "3" ]] && configure_openai=true

printf "\n"
case "$tool_choice" in
    1) write_ok "Claude Code selected" ;;
    2) write_ok "Cursor / OpenAI-compatible tools selected" ;;
    3) write_ok "Claude Code + Cursor / OpenAI-compatible tools selected" ;;
    4) write_ok "Manual configuration -- env vars will not be set" ;;
esac

# -- Step 3: Upstream keys ----------------------------------------------------

write_step "Storing upstream API key(s)..."

mkdir -p "$KIRI_DATA"

ANTHROPIC_KEY_FILE="$KIRI_DATA/upstream.key"
claude_auth_mode="api_key"   # api_key | oauth

if [[ -f "$ANTHROPIC_KEY_FILE" ]]; then
    write_ok "Anthropic key already stored -- skipping (delete $ANTHROPIC_KEY_FILE to replace)"
elif [[ "$configure_claude" == true || "$tool_choice" == "4" ]]; then
    if [[ -z "$ANTHROPIC_KEY" ]]; then
        printf "\n"
        printf "  ${WHITE}How does Claude Code authenticate?${NC}\n\n"
        printf "  ${WHITE}[1] API key (sk-ant-...)      ${GRAY}recommended — full bypass-prevention${NC}\n"
        printf "  ${WHITE}[2] Claude Pro / Max (OAuth)  ${GRAY}no API key needed, filter pipeline still active${NC}\n\n"
        read -rp "  Choice [1-2, default: 1]: " auth_choice
        [[ -z "$auth_choice" || ! "$auth_choice" =~ ^[1-2]$ ]] && auth_choice="1"
        [[ "$auth_choice" == "2" ]] && claude_auth_mode="oauth"
        printf "\n"
    fi

    if [[ "$claude_auth_mode" == "oauth" ]]; then
        printf "oauth-passthrough" > "$ANTHROPIC_KEY_FILE"
        chmod 600 "$ANTHROPIC_KEY_FILE"
        config_path="$KIRI_DATA/config.yaml"
        if [[ ! -f "$config_path" ]] || ! grep -q "oauth_passthrough" "$config_path" 2>/dev/null; then
            printf "\noauth_passthrough: true\n" >> "$config_path"
        fi
        write_ok "OAuth passthrough enabled -- no upstream API key required"
        write_info "See docs/guides/claude-pro-max.md for details"
    else
        if [[ -z "$ANTHROPIC_KEY" ]]; then
            printf "      ${YELLOW}Your key is stored only inside the Docker container as a secret.${NC}\n"
            printf "      ${YELLOW}It never appears in logs, env dumps, or docker inspect output.${NC}\n\n"
            read -rp "      Anthropic API key (sk-ant-...): " ANTHROPIC_KEY
            printf "\n"
        fi
        [[ "$ANTHROPIC_KEY" != sk-ant-* ]] && \
            fail "Expected an Anthropic key (sk-ant-...). Re-run with the correct key."
        printf "%s" "$ANTHROPIC_KEY" > "$ANTHROPIC_KEY_FILE"
        chmod 600 "$ANTHROPIC_KEY_FILE"
        write_ok "Anthropic key stored at $ANTHROPIC_KEY_FILE"
    fi
fi

OPENAI_KEY_FILE="$KIRI_DATA/openai.key"
if [[ "$configure_openai" == true ]]; then
    if [[ -f "$OPENAI_KEY_FILE" ]]; then
        write_ok "OpenAI key already stored -- skipping (delete $OPENAI_KEY_FILE to replace)"
    else
        if [[ -z "$OPENAI_KEY" ]]; then
            printf "\n"
            printf "      ${YELLOW}OpenAI upstream key -- needed only if you use GPT models via Cursor.${NC}\n"
            printf "      ${YELLOW}Press Enter to skip if you only use Claude models.${NC}\n\n"
            read -rp "      OpenAI API key (sk-..., or Enter to skip): " OPENAI_KEY
            printf "\n"
        fi
        if [[ -n "$OPENAI_KEY" ]]; then
            printf "%s" "$OPENAI_KEY" > "$OPENAI_KEY_FILE"
            chmod 600 "$OPENAI_KEY_FILE"
            write_ok "OpenAI key stored at $OPENAI_KEY_FILE"
        else
            write_info "No OpenAI key stored -- GPT model calls will use the Anthropic key fallback"
        fi
    fi
fi

# -- Step 4: Patch docker-compose.yml for openai_key if needed ----------------

if [[ "$configure_openai" == true && -f "$OPENAI_KEY_FILE" ]]; then
    compose_path="$KIRI_DIR/docker-compose.yml"
    if ! grep -q "openai_key" "$compose_path"; then
        python3 - "$compose_path" <<'PYEOF'
import sys
path = sys.argv[1]
content = open(path).read()
old = "  anthropic_key:\n    file: .kiri/upstream.key"
new = "  anthropic_key:\n    file: .kiri/upstream.key\n  openai_key:\n    file: .kiri/openai.key"
open(path, "w").write(content.replace(old, new))
PYEOF
        write_ok "docker-compose.yml updated with openai_key secret"
    else
        write_ok "docker-compose.yml already has openai_key secret"
    fi
fi

# -- Step 5: Start stack ------------------------------------------------------

write_step "Starting Kiri stack..."
write_info "First run pulls the image from ghcr.io and downloads the Ollama model (~2 GB)."
write_info "This can take 5-30 minutes depending on your connection."

docker compose --project-directory "$KIRI_DIR" up -d || \
    fail "docker compose up -d failed. See output above."
write_ok "Stack started"

# -- Step 6: Health check -----------------------------------------------------

write_step "Waiting for gateway health (up to 10 min for model download)..."

_gw_timeout=600
[[ "$CI_MODE" == true ]] && _gw_timeout=60
if ! wait_for_gateway "$_gw_timeout"; then
    write_warn "Gateway did not become healthy within ${_gw_timeout}s."
    write_warn "The model may still be downloading. Check:"
    printf "\n      docker compose --project-directory \"%s\" logs ollama-pull -f\n\n" "$KIRI_DIR"
    write_warn "Re-run this installer once the model is ready."
    exit 1
fi
write_ok "Gateway healthy at http://localhost:8765"

# -- Step 7: Developer key (API key mode only) --------------------------------

kiri_key=""
if [[ "$claude_auth_mode" != "oauth" ]]; then
    write_step "Generating your Kiri developer key..."

    raw_output=$(docker compose --project-directory "$KIRI_DIR" exec -T kiri kiri key create 2>&1)
    kiri_key=$(printf "%s" "$raw_output" | tail -1 | tr -d '[:space:]')

    [[ "$kiri_key" != kr-* ]] && fail "Key creation failed. Output: $raw_output"
    write_ok "Key: $kiri_key"
else
    write_step "OAuth mode -- skipping developer key generation"
    write_info "Claude Code will use its own OAuth session token directly"
fi

# -- Step 8: Environment variables --------------------------------------------

write_step "Setting environment variables..."

profile=$(detect_profile)
[[ ! -f "$profile" ]] && touch "$profile"

block=""
if [[ "$configure_claude" == true ]]; then
    block+="export ANTHROPIC_BASE_URL=\"http://localhost:8765\"\n"
fi
if [[ "$configure_openai" == true ]]; then
    block+="export OPENAI_BASE_URL=\"http://localhost:8765\"\n"
    block+="export OPENAI_API_BASE=\"http://localhost:8765\""
fi

if [[ -n "$block" ]]; then
    add_to_profile "$profile" "$(printf "%b" "$block")"
    [[ "$configure_claude" == true ]] && write_ok "ANTHROPIC_BASE_URL=http://localhost:8765  ($profile)"
    [[ "$configure_openai" == true ]] && write_ok "OPENAI_BASE_URL + OPENAI_API_BASE=http://localhost:8765  ($profile)"
    write_info "Run 'source $profile' or open a new terminal to activate."
else
    write_info "No env vars set (manual configuration chosen)"
fi

# -- Step 9: Autostart via systemd user service -------------------------------

write_step "Configuring autostart at login (systemd user service)..."

mkdir -p "$WRAPPER_DIR"
DOCKER_BIN="$(command -v docker)"

# Helper script: waits for Docker daemon, then starts the stack
cat > "$AUTOSTART_SCRIPT" <<SHEOF
#!/usr/bin/env bash
# Kiri autostart -- called by systemd at login
for _ in \$(seq 1 60); do
    if "$DOCKER_BIN" ps >/dev/null 2>&1; then
        "$DOCKER_BIN" compose --project-directory "$KIRI_DIR" up -d
        exit 0
    fi
    sleep 5
done
exit 1
SHEOF
chmod +x "$AUTOSTART_SCRIPT"

if command -v systemctl &>/dev/null && systemctl --user show-environment &>/dev/null 2>&1; then
    mkdir -p "$SYSTEMD_DIR"

    cat > "$SERVICE_FILE" <<SVCEOF
[Unit]
Description=Kiri Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=$AUTOSTART_SCRIPT
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
SVCEOF

    systemctl --user daemon-reload
    if systemctl --user enable "$SERVICE_NAME" 2>/dev/null; then
        write_ok "systemd user service '$SERVICE_NAME' enabled -- auto-starts at next login"
    else
        write_warn "Could not enable systemd service -- Kiri will not auto-start"
    fi

    # Enable linger so the service starts at boot (not only after interactive login)
    if command -v loginctl &>/dev/null; then
        if loginctl enable-linger "$USER" 2>/dev/null; then
            write_ok "loginctl linger enabled -- service starts at boot, not just at login"
        else
            write_info "loginctl linger unavailable -- service starts at interactive login only"
        fi
    fi
else
    write_warn "systemd user services not available on this system."
    write_info "Adding startup command to $profile instead."
    startup_block="# Start Kiri gateway on login\n$AUTOSTART_SCRIPT &"
    add_to_profile "$profile" "$(printf "%b" "$startup_block")"
    write_ok "Startup command added to $profile"
fi

# -- Step 10: CLI wrapper -----------------------------------------------------

write_step "Installing kiri CLI wrapper..."

cat > "$WRAPPER_PATH" <<WRAPEOF
#!/usr/bin/env bash
# kiri -- generated by Kiri installer. Do not edit manually.
running=\$(docker compose --project-directory "$KIRI_DIR" ps --services --filter status=running 2>/dev/null | grep "^kiri\$")
if [[ -z "\$running" ]]; then
    printf "Kiri gateway is not running. Start it with:\n  docker compose --project-directory '%s' up -d\n" "$KIRI_DIR" >&2
    exit 1
fi
docker compose --project-directory "$KIRI_DIR" exec kiri kiri "\$@"
WRAPEOF
chmod +x "$WRAPPER_PATH"

# Add wrapper dir to PATH in profile (idempotent via tagged block)
path_block="export PATH=\"\$HOME/.kiri/bin:\$PATH\""
if ! grep -q '\.kiri/bin' "$profile" 2>/dev/null; then
    printf "\n# >>> kiri-path >>>\n%s\n# <<< kiri-path <<<\n" "$path_block" >> "$profile"
    write_ok "Added $WRAPPER_DIR to PATH in $profile"
else
    write_ok "PATH already contains $WRAPPER_DIR"
fi
write_ok "kiri wrapper installed at $WRAPPER_PATH"

# --------------------------------------------------------------------------- #
# Done
# --------------------------------------------------------------------------- #

printf "\n  ${GREEN}================================${NC}\n"
printf   "  ${GREEN}Kiri installed successfully!${NC}\n"
printf   "  ${GREEN}================================${NC}\n\n"
printf   "  Gateway :  http://localhost:8765\n"
if [[ -n "$kiri_key" ]]; then
    printf "  Your key:  %s\n" "$kiri_key"
else
    printf "  Auth mode: Claude Pro/Max (OAuth passthrough)\n"
fi
printf "\n"

printf "  ${YELLOW}Next steps:${NC}\n\n"

if [[ "$configure_claude" == true ]]; then
    printf "  ${CYAN}Claude Code${NC}\n"
    printf "  -----------\n"
    if [[ "$claude_auth_mode" == "oauth" ]]; then
        printf "  OAuth passthrough is active. Just run:\n"
        printf "  ${GRAY}source %s${NC}\n" "$(detect_profile)"
        printf "  ${GRAY}claude \"hello\"${NC}\n\n"
        printf "  ${GRAY}ANTHROPIC_BASE_URL is set. Do NOT set ANTHROPIC_API_KEY.${NC}\n\n"
    else
        printf "  Set ANTHROPIC_API_KEY to your Kiri key:\n"
        printf "  ${GRAY}export ANTHROPIC_API_KEY=%s${NC}\n\n" "$kiri_key"
    fi
fi

if [[ "$configure_openai" == true ]]; then
    printf "  ${CYAN}Cursor / Windsurf${NC}\n"
    printf "  -----------------\n"
    printf "  1. Open Settings\n"
    printf "  2. Search for 'OpenAI API Key' or 'Model provider'\n"
    printf "  3. Set API Key to: %s\n" "$kiri_key"
    printf "  4. Set Base URL to: http://localhost:8765\n\n"
    printf "  ${GRAY}OPENAI_BASE_URL and OPENAI_API_BASE are set in %s.${NC}\n" "$profile"
    printf "  ${GRAY}Restart Cursor / Windsurf after sourcing your profile.${NC}\n\n"
fi

if [[ "$configure_claude" == false && "$configure_openai" == false ]]; then
    printf "  You chose manual configuration. Point your tool at:\n"
    printf "  ${GRAY}Base URL : http://localhost:8765${NC}\n"
    printf "  ${GRAY}API key  : %s${NC}\n\n" "$kiri_key"
fi

printf "  Run 'source %s' or open a new terminal to activate env vars.\n\n" "$profile"

printf "  ${GRAY}Common commands:${NC}\n"
printf "  ${GRAY}   kiri add @MyClass       -- protect a symbol${NC}\n"
printf "  ${GRAY}   kiri status             -- show what is protected${NC}\n"
printf "  ${GRAY}   kiri log --tail 20      -- recent decisions${NC}\n\n"
printf "  ${GRAY}To uninstall: ./install/linux/uninstall.sh${NC}\n\n"
