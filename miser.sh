#!/usr/bin/env bash
set -euo pipefail

# Miser v2.0 launcher for macOS / Linux
# Usage: ./miser.sh [--port 7860] [--host 0.0.0.0]

cd "$(dirname "$0")"

export PYTHONIOENCODING=utf-8
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# Auto-detect Python
if command -v python3 &>/dev/null; then
    PY=python3
elif command -v python &>/dev/null; then
    PY=python
else
    echo "ERROR: Python not found. Install it: brew install python"
    exit 1
fi

echo "Miser launcher — Ctrl+C to stop"
echo ""

exec "$PY" -u miser.py "$@"
