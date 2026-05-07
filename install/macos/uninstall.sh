#!/usr/bin/env bash
# Kiri Gateway -- macOS uninstaller
#
# Usage:
#   ./uninstall.sh
#   ./uninstall.sh --purge-data    # also deletes .kiri/ (keys, index, audit log)
#
# If you connected via connect.sh (team gateway, no local Docker),
# use disconnect.sh instead -- it only removes env vars.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
KIRI_DIR="$REPO_ROOT/kiri"
KIRI_DATA="$KIRI_DIR/.kiri"
WRAPPER_DIR="$HOME/.kiri/bin"
WRAPPER_PATH="$WRAPPER_DIR/kiri"
AUTOSTART_SCRIPT="$WRAPPER_DIR/kiri-autostart.sh"
PLIST_LABEL="io.kiri.gateway"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

PURGE_DATA=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --purge-data) PURGE_DATA=true; shift ;;
        *) printf "Unknown argument: %s\n" "$1" >&2; exit 1 ;;
    esac
done

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; CYAN=$'\033[0;36m'
YELLOW=$'\033[1;33m'; GRAY=$'\033[0;37m'; WHITE=$'\033[1;37m'; NC=$'\033[0m'

write_step() { printf "\n  ${CYAN}--> %s${NC}\n" "$1"; }
write_ok()   { printf "      ${GREEN}OK   %s${NC}\n" "$1"; }
write_info() { printf "      ${GRAY}...  %s${NC}\n" "$1"; }
write_warn() { printf "      ${YELLOW}WARN %s${NC}\n" "$1"; }

printf "\n  ${WHITE}Kiri Gateway - macOS Uninstaller${NC}\n"
printf   "  ${GRAY}=================================${NC}\n\n"

# -- Stop Docker stack --------------------------------------------------------

write_step "Stopping Docker stack..."

if ! command -v docker &>/dev/null; then
    write_info "Docker not found -- skipping (team install? Use disconnect.sh for env-only cleanup)"
elif [[ ! -d "$KIRI_DIR" ]]; then
    write_info "Kiri directory not found -- skipping"
else
    if docker compose --project-directory "$KIRI_DIR" down 2>/dev/null; then
        write_ok "Stack stopped and containers removed"
    else
        write_warn "docker compose down returned an error -- stack may already be stopped"
    fi
fi

# -- LaunchAgent --------------------------------------------------------------

write_step "Removing LaunchAgent..."

if [[ -f "$PLIST_PATH" ]]; then
    launchctl bootout "gui/$(id -u)/$PLIST_LABEL" 2>/dev/null || \
        launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    write_ok "LaunchAgent '$PLIST_LABEL' removed"
else
    write_info "LaunchAgent not found -- skipping"
fi

# -- Environment variables ----------------------------------------------------

write_step "Removing Kiri environment variables from shell profile..."

kiri_default="http://localhost:8765"

for profile in "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.profile"; do
    [[ ! -f "$profile" ]] && continue
    changed=false

    for tag in "kiri-gateway" "kiri-path"; do
        if grep -q ">>> $tag >>>" "$profile" 2>/dev/null; then
            sed -i '' "/# >>> $tag >>>/,/# <<< $tag <<</d" "$profile"
            changed=true
        fi
    done

    $changed && write_ok "Removed Kiri blocks from $profile"
done

# -- CLI wrapper and autostart script -----------------------------------------

write_step "Removing kiri CLI wrapper..."

[[ -f "$WRAPPER_PATH" ]]     && { rm -f "$WRAPPER_PATH";     write_ok "Removed $WRAPPER_PATH"; }
[[ -f "$AUTOSTART_SCRIPT" ]] && { rm -f "$AUTOSTART_SCRIPT"; write_ok "Removed $AUTOSTART_SCRIPT"; }

if [[ -d "$WRAPPER_DIR" ]] && [[ -z "$(ls -A "$WRAPPER_DIR" 2>/dev/null)" ]]; then
    rm -rf "$WRAPPER_DIR"
fi

# -- Data directory -----------------------------------------------------------

write_step "Data directory..."

if [[ "$PURGE_DATA" == true ]]; then
    if [[ -d "$KIRI_DATA" ]]; then
        rm -rf "$KIRI_DATA"
        write_ok "Deleted $KIRI_DATA"
    else
        write_info "Not found -- skipping"
    fi
else
    write_info "Preserved: $KIRI_DATA"
    write_info "Re-run with --purge-data to delete keys, index, and audit log"
fi

# -- Done ---------------------------------------------------------------------

printf "\n  ${GREEN}Kiri uninstalled.${NC}\n\n"
if [[ "$PURGE_DATA" == false && -d "$KIRI_DATA" ]]; then
    printf "  ${GRAY}Data preserved at: %s${NC}\n" "$KIRI_DATA"
fi
printf "  ${GRAY}To reinstall: ./install/macos/install.sh${NC}\n\n"
