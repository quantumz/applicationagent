#!/bin/bash
# ApplicationAgent Uninstaller
# Removes everything install.sh put down

set -e

print_header() { echo; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; echo "  $1"; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; echo; }
print_step()   { echo "  ▸ $1"; }
print_ok()     { echo "  ✓ $1"; }
print_warn()   { echo "  ⚠ $1"; }
print_skip()   { echo "  — $1 (not found, skipping)"; }

INSTALL_DIR="$HOME/.local/applicationagent"
DEFAULT_VENV="$INSTALL_DIR/.venv"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

# ── Detect venv — may be custom (CLI power-user install) ──────────────────────
# Read from CLI wrapper before we remove anything
DETECTED_VENV=""
if [ -f "$BIN_DIR/applicationagent-ui" ]; then
    DETECTED_VENV=$(grep -oP 'source "\K[^"]+(?=/bin/activate)' "$BIN_DIR/applicationagent-ui" 2>/dev/null || true)
fi
if [ -z "$DETECTED_VENV" ] && [ -f "$BIN_DIR/applicationagent" ]; then
    DETECTED_VENV=$(grep -oP 'source "\K[^"]+(?=/bin/activate)' "$BIN_DIR/applicationagent" 2>/dev/null || true)
fi
VENV_DIR="${DETECTED_VENV:-$DEFAULT_VENV}"

# Is the venv inside the install dir? If so, rm -rf handles it — no separate prompt.
VENV_IS_INTERNAL=false
case "$VENV_DIR" in
    "$INSTALL_DIR"/*) VENV_IS_INTERNAL=true ;;
esac

print_header "ApplicationAgent Uninstaller"

# ── Confirm ────────────────────────────────────────────────────────────────────
echo "  This will remove:"
echo "    $INSTALL_DIR"
if [ "$VENV_IS_INTERNAL" = "true" ]; then
    echo "    $VENV_DIR  (inside install dir — removed with it)"
else
    echo "    $VENV_DIR  (external venv — you will be asked)"
fi
echo "    $DESKTOP_DIR/applicationagent.desktop"
echo "    $HOME/Desktop/applicationagent.desktop"
echo "    $BIN_DIR/applicationagent"
echo "    $BIN_DIR/applicationagent-ui"
echo "    PATH entries from .bashrc / .zshrc"
echo
read -rp "  Proceed? [y/N]: " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "  Aborted."
    exit 0
fi

# ── Kill running process ───────────────────────────────────────────────────────
print_header "Stopping ApplicationAgent"
if pgrep -f "applicationagent.*app.py" >/dev/null 2>&1; then
    pkill -f "applicationagent.*app.py" && print_ok "Stopped running process"
else
    print_skip "No running process found"
fi

# ── App files + internal venv ─────────────────────────────────────────────────
print_header "Removing Application Files"
if [ -d "$INSTALL_DIR" ]; then
    rm -rf "$INSTALL_DIR"
    print_ok "Removed $INSTALL_DIR"
    if [ "$VENV_IS_INTERNAL" = "true" ]; then
        print_ok "Virtual environment removed with install dir"
    fi
else
    print_skip "$INSTALL_DIR"
fi

# ── External venv (CLI power-user only) ───────────────────────────────────────
if [ "$VENV_IS_INTERNAL" = "false" ]; then
    print_header "Virtual Environment"
    if [ -d "$VENV_DIR" ]; then
        read -rp "  Remove external virtual environment at $VENV_DIR? [y/N]: " REMOVE_VENV
        if [[ "$REMOVE_VENV" =~ ^[Yy]$ ]]; then
            rm -rf "$VENV_DIR"
            print_ok "Removed $VENV_DIR"
        else
            print_warn "Kept $VENV_DIR — delete manually if needed"
        fi
    else
        print_skip "$VENV_DIR"
    fi
fi

# ── Desktop entries ───────────────────────────────────────────────────────────
print_header "Removing Desktop Entries"

if [ -f "$DESKTOP_DIR/applicationagent.desktop" ]; then
    rm -f "$DESKTOP_DIR/applicationagent.desktop"
    print_ok "Removed $DESKTOP_DIR/applicationagent.desktop"
else
    print_skip "$DESKTOP_DIR/applicationagent.desktop"
fi

if [ -f "$HOME/Desktop/applicationagent.desktop" ]; then
    rm -f "$HOME/Desktop/applicationagent.desktop"
    print_ok "Removed $HOME/Desktop/applicationagent.desktop"
else
    print_skip "$HOME/Desktop/applicationagent.desktop"
fi

if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    print_ok "Desktop database updated"
fi

# ── CLI wrappers ──────────────────────────────────────────────────────────────
print_header "Removing CLI Wrappers"

for WRAPPER in applicationagent applicationagent-ui; do
    if [ -f "$BIN_DIR/$WRAPPER" ]; then
        rm -f "$BIN_DIR/$WRAPPER"
        print_ok "Removed $BIN_DIR/$WRAPPER"
    else
        print_skip "$BIN_DIR/$WRAPPER"
    fi
done

# ── PATH entries ──────────────────────────────────────────────────────────────
print_header "Cleaning Shell RC Files"

for RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$RC" ] && grep -q "$BIN_DIR" "$RC" 2>/dev/null; then
        sed -i "\|export PATH=\"$BIN_DIR:\\\$PATH\"|d" "$RC"
        print_ok "Removed PATH entry from $RC"
    else
        print_skip "$RC (no entry found)"
    fi
done

# ── Done ──────────────────────────────────────────────────────────────────────
print_header "Uninstall Complete"
echo "  ApplicationAgent has been removed."
echo "  Run install.sh to reinstall from scratch."
echo
