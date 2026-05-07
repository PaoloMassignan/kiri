#!/usr/bin/env bash
# Kiri Gateway -- team developer disconnector
#
# Removes the environment variables added by connect.sh.
# Does not touch Docker, LaunchAgents, or the kiri CLI wrapper.
#
# If you ran the full install.sh (local Docker), use uninstall.sh instead.

set -euo pipefail

GREEN=$'\033[0;32m'; CYAN=$'\033[0;36m'
GRAY=$'\033[0;37m'; WHITE=$'\033[1;37m'; NC=$'\033[0m'

write_step() { printf "\n  ${CYAN}--> %s${NC}\n" "$1"; }
write_ok()   { printf "      ${GREEN}OK   %s${NC}\n" "$1"; }
write_info() { printf "      ${GRAY}...  %s${NC}\n" "$1"; }

printf "\n  ${WHITE}Kiri Gateway - Disconnect from team gateway${NC}\n"
printf   "  ${GRAY}=============================================${NC}\n\n"

write_step "Removing Kiri environment variables from shell profile..."

removed=0
for profile in "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.profile"; do
    [[ ! -f "$profile" ]] && continue

    if grep -q ">>> kiri-gateway >>>" "$profile" 2>/dev/null; then
        sed -i '' '/# >>> kiri-gateway >>>/,/# <<< kiri-gateway <<</d' "$profile"
        write_ok "Removed kiri-gateway block from $profile"
        removed=$(( removed + 1 ))
    fi
done

if [[ $removed -eq 0 ]]; then
    printf "\n  ${GRAY}Nothing to remove -- no Kiri env vars found in shell profiles.${NC}\n\n"
    exit 0
fi

printf "\n  ${GREEN}Disconnected.${NC}\n\n"
printf "  ${GRAY}Open a new terminal (or run 'source ~/.zshrc') for the change to take effect.${NC}\n"
printf "  ${GRAY}To reconnect: ./install/macos/connect.sh${NC}\n\n"
