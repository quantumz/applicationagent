#!/bin/bash
# ApplicationAgent Installer
# Supports Linux (Desktop + CLI) and macOS (CLI)

set -e

# ── flags ──────────────────────────────────────────────────────────────────────
CLEAN_INSTALL=false
for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN_INSTALL=true ;;
    esac
done

# ── helpers ────────────────────────────────────────────────────────────────────
print_header() { echo; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; echo "  $1"; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; echo; }
print_step()   { echo "  ▸ $1"; }
print_ok()     { echo "  ✓ $1"; }
print_warn()   { echo "  ⚠ $1"; }
print_err()    { echo; echo "  ERROR: $1"; echo; }

# ── OS detection ──────────────────────────────────────────────────────────────
OS="$(uname -s)"
case "${OS}" in
    Linux*)  PLATFORM=Linux ;;
    Darwin*) PLATFORM=Mac ;;
    *)       print_err "Unsupported OS: ${OS}"; exit 1 ;;
esac

print_header "ApplicationAgent Installer"
print_ok "Platform: $PLATFORM"

# ── Python check ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    print_err "Python 3 is not installed."
    echo "  Install it with:"
    echo "    sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED="3.11"
if [ "$(printf '%s\n' "$REQUIRED" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED" ]; then
    print_err "Python 3.11+ required (you have Python $PYTHON_VERSION)."
    echo "  Install it with: sudo apt install python3.11 python3.11-venv"
    exit 1
fi
print_ok "Python $PYTHON_VERSION"

# ── Install mode ──────────────────────────────────────────────────────────────
print_header "Choose Install Mode"

if [ "$PLATFORM" = "Linux" ]; then
    echo "  1) Desktop  (recommended)"
    echo "     — Single-click launcher added to your applications menu"
    echo "     — Opens the web UI automatically in your browser"
    echo "     — Best for most users"
    echo
    echo "  2) CLI only"
    echo "     — Adds 'applicationagent' command to your terminal"
    echo "     — You control when and how to run it"
    echo "     — Best for power users and servers"
    echo
    read -rp "  Choose [1/2, default=1]: " MODE_CHOICE
    MODE_CHOICE="${MODE_CHOICE:-1}"
else
    # macOS — no GNOME, CLI only
    echo "  macOS detected — installing CLI mode only."
    MODE_CHOICE="2"
fi

if [ "$MODE_CHOICE" = "2" ]; then
    INSTALL_MODE="cli"
else
    INSTALL_MODE="desktop"
fi
print_ok "Mode: $INSTALL_MODE"

# ── Install directory ─────────────────────────────────────────────────────────
INSTALL_DIR="$HOME/.local/applicationagent"
print_step "Application will be installed to: $INSTALL_DIR"

# ── Reinstall guard ────────────────────────────────────────────────────────────
if [ -d "$INSTALL_DIR" ]; then
    if [ "$CLEAN_INSTALL" = "true" ]; then
        print_step "Clean install — removing existing installation..."
        rm -rf "$INSTALL_DIR"
        print_ok "Existing installation removed"
    else
        print_warn "Existing installation detected at $INSTALL_DIR"
        echo "  Your .env and data/ will be preserved."
        echo "  To wipe everything and start fresh: bash install.sh --clean"
        echo
        read -rp "  Reinstall over existing installation? [y/N]: " REINSTALL
        if [[ ! "$REINSTALL" =~ ^[Yy]$ ]]; then
            echo "  Aborted."
            exit 0
        fi
    fi
fi

# ── Virtual environment location ──────────────────────────────────────────────
if [ "$INSTALL_MODE" = "desktop" ]; then
    VENV_DIR="$INSTALL_DIR/.venv"
    print_step "Virtual environment: $VENV_DIR"
else
    print_header "Python Virtual Environment"
    echo "  Where should the virtual environment be created?"
    echo "  Press Enter to use the default (inside the install directory)."
    echo
    read -rp "  Path [default: $INSTALL_DIR/.venv]: " VENV_INPUT
    VENV_DIR="${VENV_INPUT:-$INSTALL_DIR/.venv}"
    print_ok "Using: $VENV_DIR"
fi

# ── Copy application files ────────────────────────────────────────────────────
print_header "Installing Application Files"

mkdir -p "$INSTALL_DIR"

# Use rsync if available (excludes .git and runtime dirs cleanly)
if command -v rsync &>/dev/null; then
    rsync -a \
        --exclude='.git/' \
        --exclude='data/' \
        --exclude='*.db' \
        --exclude='output/' \
        --exclude='logs/' \
        --exclude='venv/' \
        --exclude='.venv/' \
        --exclude='tests/' \
        --exclude='*.pyc' \
        --exclude='__pycache__/' \
        --exclude='.env' \
        --exclude='resumes/' \
        ./ "$INSTALL_DIR/"
else
    cp -r ./* "$INSTALL_DIR/"
    rm -rf "$INSTALL_DIR/.git" \
           "$INSTALL_DIR/venv" \
           "$INSTALL_DIR/.venv" \
           "$INSTALL_DIR/tests" \
           "$INSTALL_DIR/data" \
           "$INSTALL_DIR/__pycache__"
    find "$INSTALL_DIR" -maxdepth 2 -name '*.db' -delete 2>/dev/null || true
fi
print_ok "Files copied to $INSTALL_DIR"

# ── Runtime directories ───────────────────────────────────────────────────────
mkdir -p \
    "$INSTALL_DIR/data" \
    "$INSTALL_DIR/output/pdf" \
    "$INSTALL_DIR/output/excel" \
    "$INSTALL_DIR/logs"
print_ok "Runtime directories created"

# ── .env setup ────────────────────────────────────────────────────────────────
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.sample" "$INSTALL_DIR/.env"
    print_ok ".env created"
else
    print_ok ".env already exists — not overwritten"
fi

# ── Virtual environment ───────────────────────────────────────────────────────
print_header "Setting Up Python Environment"

print_step "Creating virtual environment..."
mkdir -p "$(dirname "$VENV_DIR")"
python3 -m venv "$VENV_DIR"
print_ok "Virtual environment ready"

print_step "Installing Python dependencies (this takes about a minute)..."
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --quiet
print_ok "Python packages installed"

print_step "Installing Playwright browser (Chromium — needed for job scraping)..."
"$VENV_DIR/bin/playwright" install chromium 2>/dev/null
print_ok "Chromium installed"

# ── Desktop mode: launcher script + .desktop file ─────────────────────────────
if [ "$INSTALL_MODE" = "desktop" ]; then
    print_header "Creating Desktop Launcher"

    PORT=8080
    LAUNCHER="$INSTALL_DIR/launch.sh"
    LOG_FILE="$INSTALL_DIR/logs/ui.log"

    # Generate launch.sh — bakes in install-time paths
    cat > "$LAUNCHER" << LAUNCHEOF
#!/bin/bash
# ApplicationAgent — Desktop Launcher
# Auto-generated by install.sh — do not edit paths manually

INSTALL_DIR="${INSTALL_DIR}"
VENV_DIR="${VENV_DIR}"
PORT=${PORT}
URL="http://localhost:\${PORT}"
LOG="${LOG_FILE}"

open_browser() {
    local url="\$1"
    if command -v xdg-open &>/dev/null && xdg-open "\$url" 2>/dev/null; then
        return 0
    fi
    for browser in firefox chromium chromium-browser google-chrome brave-browser; do
        if command -v "\$browser" &>/dev/null; then
            "\$browser" "\$url" &
            return 0
        fi
    done
    echo ""
    echo "  ┌─────────────────────────────────────────┐"
    echo "  │  ApplicationAgent is running             │"
    echo "  │                                          │"
    echo "  │  Open your browser and go to:            │"
    echo "  │  http://localhost:8080                   │"
    echo "  └─────────────────────────────────────────┘"
    echo ""
}

# If already running, just open the browser
if curl -s "\${URL}" >/dev/null 2>&1; then
    open_browser "\${URL}"
    exit 0
fi

# Start server, redirect output to log
mkdir -p "\$(dirname "\${LOG}")"
export APPLICATIONAGENT_ROOT="\${INSTALL_DIR}"
export PYTHONUNBUFFERED=1
"\${VENV_DIR}/bin/python" "\${INSTALL_DIR}/ui/app.py" >> "\${LOG}" 2>&1 &
FLASK_PID=\$!

echo "Starting ApplicationAgent (PID \${FLASK_PID})..."
echo "Log: \${LOG}"

# Wait up to 10s for Flask to respond
for i in \$(seq 1 20); do
    if curl -s "\${URL}" >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

open_browser "\${URL}"

# Keep process running
wait \$FLASK_PID
LAUNCHEOF

    chmod +x "$LAUNCHER"
    print_ok "Launcher: $LAUNCHER"

    # GNOME .desktop file
    DESKTOP_DIR="$HOME/.local/share/applications"
    mkdir -p "$DESKTOP_DIR"

    # Use bundled icon if present, fall back to generic system icon
    ICON_PATH="$INSTALL_DIR/ui/static/icon.png"
    if [ ! -f "$ICON_PATH" ]; then
        ICON_PATH="applications-internet"
    fi

    cat > "$DESKTOP_DIR/applicationagent.desktop" << DESKTOPEOF
[Desktop Entry]
Version=1.0
Type=Application
Name=ApplicationAgent
GenericName=Job Screening Agent
Comment=Screen jobs before applying — stop wasting time on auto-rejections
Exec=${LAUNCHER}
Icon=${ICON_PATH}
Terminal=false
Categories=Office;Network;
Keywords=jobs;resume;career;screening;
StartupNotify=true
DESKTOPEOF

    chmod +x "$DESKTOP_DIR/applicationagent.desktop"

    # Register with GNOME desktop database
    if command -v update-desktop-database &>/dev/null; then
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    fi

    # Attempt live menu refresh (GNOME 3.x+ — works without logout on most systems)
    if command -v gio &>/dev/null; then
        gio mime x-scheme-handler/http >/dev/null 2>&1 || true
    fi
    if command -v dbus-send &>/dev/null; then
        dbus-send --session \
            --dest=org.gnome.Shell \
            --type=method_call \
            /org/gnome/Shell \
            org.gnome.Shell.Eval \
            string:'imports.gi.Shell.AppSystem.get_default().lookup_startup_wmclass("applicationagent")' \
            2>/dev/null || true
    fi

    print_ok "Desktop entry installed: $DESKTOP_DIR/applicationagent.desktop"
    print_warn "If it doesn't appear in your menu immediately, log out and back in once"

    # Drop a copy on the Desktop — visible immediately, no logout needed
    DESKTOP_SHORTCUT="$HOME/Desktop"
    if [ -d "$DESKTOP_SHORTCUT" ]; then
        cp "$DESKTOP_DIR/applicationagent.desktop" "$DESKTOP_SHORTCUT/"
        chmod +x "$DESKTOP_SHORTCUT/applicationagent.desktop"
        gio set "$DESKTOP_SHORTCUT/applicationagent.desktop" metadata::trusted true 2>/dev/null || true
        print_ok "Desktop icon created — double-click it to launch"
    fi
fi

# ── CLI mode: command wrapper + PATH ──────────────────────────────────────────
if [ "$INSTALL_MODE" = "cli" ]; then
    print_header "CLI Setup"

    BIN_DIR="$HOME/.local/bin"
    mkdir -p "$BIN_DIR"

    cat > "$BIN_DIR/applicationagent" << CLIEOF
#!/bin/bash
source "${VENV_DIR}/bin/activate"
cd "${INSTALL_DIR}"
python applicationagent.py "\$@"
CLIEOF
    chmod +x "$BIN_DIR/applicationagent"
    print_ok "CLI wrapper: $BIN_DIR/applicationagent"

    # Update PATH in shell rc files
    PATH_UPDATED=0
    for RC in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [ -f "$RC" ] && ! grep -q "$BIN_DIR" "$RC" 2>/dev/null; then
            echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$RC"
            print_ok "Added $BIN_DIR to PATH in $RC"
            PATH_UPDATED=1
        fi
    done

    # Also add a UI launcher to bin
    cat > "$BIN_DIR/applicationagent-ui" << UIEOF
#!/bin/bash
export APPLICATIONAGENT_ROOT="${INSTALL_DIR}"
cd "${INSTALL_DIR}"
"${VENV_DIR}/bin/python" ui/app.py
UIEOF
    chmod +x "$BIN_DIR/applicationagent-ui"
    print_ok "UI launcher: applicationagent-ui"
fi

# ── Optional: pre-configure API key during CLI install ────────────────────────
if [ "$INSTALL_MODE" = "cli" ]; then
    echo
    read -rp "  Enter your Anthropic API key now (or press Enter to skip): " API_KEY_INPUT
    if [[ "$API_KEY_INPUT" == sk-ant-* ]]; then
        INSTALL_DIR="$INSTALL_DIR" ANTHROPIC_KEY_INPUT="$API_KEY_INPUT" \
            "$VENV_DIR/bin/python" - << 'PYEOF'
import os, sys
sys.path.insert(0, os.environ['INSTALL_DIR'])
from core.database import init_db
from core.keystore import set_key
init_db()
set_key(os.environ['ANTHROPIC_KEY_INPUT'])
print('  \u2713 API key configured')
PYEOF
    else
        echo "  — Skipped. Enter your key when you first launch the app."
    fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
print_header "Installation Complete!"

if [ "$INSTALL_MODE" = "desktop" ]; then
    cat << 'DONEMSG'
  HOW TO GET STARTED
  ──────────────────

  1. Open "ApplicationAgent" from your applications menu
     (press the Super key and search for it, or find it in Office/Internet)

     The app will open automatically in your browser.

  2. First time only — enter your Anthropic API key
     ┌─────────────────────────────────────────────────────┐
     │  A prompt will appear asking for your API key.      │
     │  Get a free key at: https://console.anthropic.com   │
     │  Sign up → API Keys → Create Key → paste it in.    │
     └─────────────────────────────────────────────────────┘

  3. Click "+ Resume" to upload your resume and set up job searches.

  4. Click "Analyze Job" to paste any job description and get an instant
     AI analysis of whether you should apply.

  5. Click "Run" to scrape job boards and analyze them in bulk.

  That's it. Everything else is explained inside the app.

  To upgrade (keep your data):  bash install.sh
  To start completely fresh:    bash install.sh --clean

DONEMSG
else
    echo "  HOW TO GET STARTED"
    echo "  ──────────────────"
    echo
    if [ "$PATH_UPDATED" = "1" ]; then
        echo "  First, reload your terminal or run:"
        echo "    source ~/.bashrc"
        echo
    fi
    echo "  Command-line usage:"
    echo "    applicationagent <resume_type>"
    echo "    Example: applicationagent my_resume"
    echo
    echo "  Web UI:"
    echo "    applicationagent-ui"
    echo "    Then open: http://localhost:8080"
    echo
    echo "  Setup:"
    echo "  1. Start the app and enter your Anthropic API key when prompted."
    echo "     Get a key at: https://console.anthropic.com"
    echo "  2. Add your resume to: $INSTALL_DIR/resumes/<name>/<name>.txt"
    echo "     See: $INSTALL_DIR/resumes/README.MD"
    echo
    echo "  To upgrade (keep your data):  bash install.sh"
    echo "  To start completely fresh:    bash install.sh --clean"
    echo
fi
