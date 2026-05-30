#!/usr/bin/env bash
# Miser MCP Server v1.5 launcher for macOS / Linux.
# Usage: ./mcp_server.sh
#        MISER_URL=http://localhost:7860 ./mcp_server.sh
set -euo pipefail

cd "$(dirname "$0")"

export PYTHONIOENCODING=utf-8

PY="${PYTHON:-python3}"
exec "$PY" -u mcp_server.py
