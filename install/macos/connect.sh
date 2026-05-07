#!/usr/bin/env bash
# Kiri Gateway -- team developer connector
#
# Configures your machine to route LLM traffic through a shared Kiri
# gateway that your team admin has already set up.
# No Docker required. No sudo required.
#
# Usage:
#   ./connect.sh
#   ./connect.sh --gateway-url http://kiri.internal:8765 --kiri-key kr-abc...

set -euo pipefail

GATEWAY_URL=""
KIRI_KEY=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --gateway-url) GATEWAY_URL="$2"; shift 2 ;;
        --kiri-key)    KIRI_KEY="$2";    shift 2 ;;
        *) printf "Unknown argument: %s\n" "$1" >&2; exit 1 ;;
    esac
done

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; CYAN=$'\033[0;36m'
YELLOW=$'\033[1;33m'; GRAY=$'\033[0;37m'; WHITE=$'\033[1;37m'; NC=$'\033[0m'

write_step() { printf "\n  ${CYAN}--> %s${NC}\n" "$1"; }
write_ok()   { printf "      ${GREEN}OK   %s${NC}\n" "$1"; }
write_info() { printf "      ${GRAY}...  %s${NC}\n" "$1"; }
write_warn() { printf "      ${YELLOW}WARN %s${NC}\n" "$1"; }
fail()       { printf "\n  ${RED}ERROR: %s${NC}\n\n" "$1" >&2; exit 1; }

detect_profile() {
    case "${SHELL:-}" in
        */zsh)  printf "%s/.zshrc" "$HOME" ;;
        */bash) printf "%s/.bash_profile" "$HOME" ;;
        *)      printf "%s/.profile" "$HOME" ;;
    esac
}

printf "\n  ${WHITE}Kiri Gateway - Connect to team gateway${NC}\n"
printf   "  ${GRAY}=======================================${NC}\n\n"

# -- Step 1: Gateway URL ------------------------------------------------------

write_step "Gateway URL..."

if [[ -z "$GATEWAY_URL" ]]; then
    printf "      ${YELLOW}Your admin should have given you the gateway address.${NC}\n\n"
    read -rp "      Gateway URL (e.g. http://kiri.internal:8765): " GATEWAY_URL
    printf "\n"
fi

GATEWAY_URL="${GATEWAY_URL%/}"
[[ "$GATEWAY_URL" =~ ^https?:// ]] || \
    fail "URL must start with http:// or https://  Got: '$GATEWAY_URL'"
write_ok "Gateway: $GATEWAY_URL"

# -- Step 2: Kiri key ---------------------------------------------------------

write_step "Your Kiri key..."

if [[ -z "$KIRI_KEY" ]]; then
    printf "      ${YELLOW}Your admin issues personal kr- keys. Ask them if you don't have one.${NC}\n\n"
    read -rp "      Kiri key (kr-...): " KIRI_KEY
    printf "\n"
fi

[[ "$KIRI_KEY" == kr-* ]] || fail "Expected a Kiri key starting with kr-  Got: '$KIRI_KEY'"
write_ok "Key: $KIRI_KEY"

# -- Step 3: Verify connectivity ----------------------------------------------

write_step "Verifying gateway connectivity..."

http_code=$(curl -sf -o /dev/null -w "%{http_code}" "$GATEWAY_URL/health" 2>/dev/null || true)
if [[ "$http_code" == "200" ]]; then
    write_ok "Gateway responded: HTTP 200"
else
    fail "Could not reach $GATEWAY_URL/health (HTTP $http_code) -- is the gateway running?"
fi

# -- Step 4: Tool selection ---------------------------------------------------

write_step "Which tools do you want to route through Kiri?"
printf "\n"
printf "  ${WHITE}[1] Claude Code                       (sets ANTHROPIC_BASE_URL)${NC}\n"
printf "  ${WHITE}[2] Cursor / Windsurf / OpenAI tools  (sets OPENAI_BASE_URL)${NC}\n"
printf "  ${WHITE}[3] Both${NC}\n"
printf "  ${GRAY}[4] None -- I will configure my tools manually${NC}\n"
printf "\n"
read -rp "  Choice [1-4, default: 1]: " tool_choice
[[ -z "$tool_choice" || ! "$tool_choice" =~ ^[1-4]$ ]] && tool_choice="1"

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

# -- Step 5: Environment variables --------------------------------------------

write_step "Setting environment variables..."

profile=$(detect_profile)
[[ ! -f "$profile" ]] && touch "$profile"

block=""
if [[ "$configure_claude" == true ]]; then
    block+="export ANTHROPIC_BASE_URL=\"$GATEWAY_URL\"\n"
fi
if [[ "$configure_openai" == true ]]; then
    block+="export OPENAI_BASE_URL=\"$GATEWAY_URL\"\n"
    block+="export OPENAI_API_BASE=\"$GATEWAY_URL\""
fi

if [[ -n "$block" ]]; then
    tag="kiri-gateway"
    if grep -q ">>> $tag >>>" "$profile" 2>/dev/null; then
        sed -i '' "/# >>> $tag >>>/,/# <<< $tag <<</d" "$profile"
    fi
    printf "\n# >>> %s >>>\n%b\n# <<< %s <<<\n" "$tag" "$block" "$tag" >> "$profile"

    [[ "$configure_claude" == true ]] && write_ok "ANTHROPIC_BASE_URL=$GATEWAY_URL  ($profile)"
    [[ "$configure_openai" == true ]] && write_ok "OPENAI_BASE_URL + OPENAI_API_BASE=$GATEWAY_URL  ($profile)"
    write_info "Run 'source $profile' or open a new terminal to activate."
else
    write_info "No env vars set (manual configuration chosen)"
fi

# -- Done ---------------------------------------------------------------------

printf "\n  ${GREEN}=======================================${NC}\n"
printf   "  ${GREEN}Connected to Kiri gateway!${NC}\n"
printf   "  ${GREEN}=======================================${NC}\n\n"
printf   "  Gateway :  %s\n" "$GATEWAY_URL"
printf   "  Your key:  %s\n\n" "$KIRI_KEY"

printf "  ${YELLOW}Next steps:${NC}\n\n"

if [[ "$configure_claude" == true ]]; then
    printf "  ${CYAN}Claude Code${NC}\n"
    printf "  -----------\n"
    printf "  Set ANTHROPIC_API_KEY to your Kiri key:\n"
    printf "  ${GRAY}export ANTHROPIC_API_KEY=%s${NC}\n\n" "$KIRI_KEY"
fi

if [[ "$configure_openai" == true ]]; then
    printf "  ${CYAN}Cursor / Windsurf${NC}\n"
    printf "  -----------------\n"
    printf "  1. Open Settings\n"
    printf "  2. Search for 'OpenAI API Key' or 'Model provider'\n"
    printf "  3. Set API Key to: %s\n" "$KIRI_KEY"
    printf "  4. Set Base URL to: %s\n\n" "$GATEWAY_URL"
fi

if [[ "$configure_claude" == false && "$configure_openai" == false ]]; then
    printf "  Point your tool at:\n"
    printf "  ${GRAY}Base URL : %s${NC}\n" "$GATEWAY_URL"
    printf "  ${GRAY}API key  : %s${NC}\n\n" "$KIRI_KEY"
fi

printf "  ${GRAY}To disconnect: ./install/macos/disconnect.sh${NC}\n\n"
