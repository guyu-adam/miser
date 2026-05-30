#!/usr/bin/env bash
# Miser v2.0 installer.
# Installs Python deps, optionally pulls a model, sets up auto-start.
#
# Usage:  bash scripts/install.sh
set -euo pipefail

MISER_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

green()  { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
red()    { echo -e "\033[31m$*\033[0m"; }
bold()   { echo -e "\033[1m$*\033[0m"; }

bold "=========================================="
bold "   Miser v2.0  --  Installer"
bold "=========================================="
echo ""

# ── 1. Python check ───────────────────────────────────────────────────────
PY_OK=$("$PYTHON" -c "import sys; print(sys.version_info >= (3,10))" 2>/dev/null || echo "False")
if [[ "$PY_OK" != "True" ]]; then
    red "X Python 3.10+ required (found: $("$PYTHON" --version 2>&1))"
    exit 1
fi
green "V $("$PYTHON" --version)"

# ── 2. Python dependencies ────────────────────────────────────────────────
yellow "> Installing Python dependencies..."
"$PYTHON" -m pip install --quiet flask rich requests
green "V flask rich requests"

# ── 3. pip install miser (editable) ───────────────────────────────────────
yellow "> Installing miser CLI..."
"$PYTHON" -m pip install --quiet -e "$MISER_DIR"
green "V miser CLI ready (try: miser --version)"

# ── 4. Auto-start setup ───────────────────────────────────────────────────
OS=$(uname -s)
if [[ "$OS" == "Darwin" ]]; then
    PLIST_DEST="$HOME/Library/LaunchAgents/com.miser.plist"
    cat > "$PLIST_DEST" << PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.miser</string>
    <key>ProgramArguments</key>
    <array>
        <string>$MISER_DIR/miser.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/miser.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/miser.err</string>
</dict>
</plist>
PLIST_EOF
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    launchctl load "$PLIST_DEST"
    green "V macOS LaunchAgent installed -- Miser starts automatically on login"
elif [[ "$OS" == "Linux" ]]; then
    SERVICE_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SERVICE_DIR"
    cat > "$SERVICE_DIR/miser.service" << UNIT_EOF
[Unit]
Description=Miser v2.0 Local AI Co-processor
After=network.target

[Service]
Type=simple
ExecStart=$MISER_DIR/miser.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT_EOF
    systemctl --user daemon-reload
    systemctl --user enable miser
    systemctl --user start miser
    green "V systemd user service installed -- Miser starts automatically on login"
else
    yellow "! Windows: auto-start not yet supported. Run miser.bat manually or on login."
fi

# ── 5. Done ───────────────────────────────────────────────────────────────
echo ""
bold "=========================================="
bold "   Miser v2.0 installed successfully"
bold "=========================================="
echo "  Start  : miser"
echo "  Server : http://localhost:7860"
echo "  Logs   : /tmp/miser.log"
echo "  Stop   : bash $MISER_DIR/scripts/start.sh --stop"
echo ""
yellow "Miser auto-detects Ollama, LM Studio, llama.cpp, vLLM."
yellow "If no LLM backend: zero-token file ops still work."
