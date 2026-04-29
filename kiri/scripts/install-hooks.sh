#!/bin/bash
# Install git hooks for this repository.
# Run once after cloning: bash scripts/install-hooks.sh

HOOKS_DIR="$(git rev-parse --git-dir)/hooks"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

install_hook() {
    local name="$1"
    local src="$SCRIPT_DIR/hooks/$name"
    local dst="$HOOKS_DIR/$name"

    if [ ! -f "$src" ]; then
        echo "WARNING: $src not found, skipping"
        return
    fi

    cp "$src" "$dst"
    chmod +x "$dst"
    echo "Installed $name -> $dst"
}

mkdir -p "$HOOKS_DIR"
install_hook pre-commit

echo "Done. Hooks are active."
