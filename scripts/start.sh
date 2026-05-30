#!/usr/bin/env bash
# Miser v1.5 launcher script.
# Auto-detects backend + model. No hardcoded model name.
#
# Usage:
#   bash scripts/start.sh                  # auto-detect everything
#   MISER_MODEL=gemma4:latest bash scripts/start.sh
#   bash scripts/start.sh --stop

set -euo pipefail

MISER_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${MISER_PORT:-7860}"
PIDFILE="/tmp/miser.pid"
LOGFILE="/tmp/miser.log"

green()  { echo -e "\033[32m$*\033[0m"; }
yellow() { echo -e "\033[33m$*\033[0m"; }
red()    { echo -e "\033[31m$*\033[0m"; }

# ── stop ──────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--stop" ]]; then
    if [[ -f "$PIDFILE" ]]; then
        kill "$(cat "$PIDFILE")" 2>/dev/null && green "Miser stopped." || yellow "Already stopped."
        rm -f "$PIDFILE"
    else
        pkill -f "miser\.py" 2>/dev/null && green "Miser stopped." || yellow "Not running."
    fi
    exit 0
fi

# ── already running? ──────────────────────────────────────────────────────
if curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1; then
    green "Miser already running on port $PORT."
    curl -s "http://localhost:$PORT/status" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  model={d.get(\"model\",\"?\")}  tasks={d.get(\"count\",0)}')
" 2>/dev/null || true
    exit 0
fi

# ── ensure Ollama is running ──────────────────────────────────────────────
if ! pgrep -x ollama >/dev/null 2>&1; then
    if command -v ollama &>/dev/null; then
        yellow "Starting Ollama..."
        OLLAMA_KEEP_ALIVE=-1 ollama serve > /tmp/ollama.log 2>&1 &
        sleep 3
    fi
fi

# ── launch ────────────────────────────────────────────────────────────────
PYTHON="${PYTHON:-python3}"
yellow "Starting Miser v1.5 (auto-detecting backend + model)..."
cd "$MISER_DIR"

MODEL_ARG=""
if [[ -n "${MISER_MODEL:-}" ]]; then
    MODEL_ARG="--model $MISER_MODEL"
fi

"$PYTHON" -u miser.py $MODEL_ARG > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

# ── wait for ready ────────────────────────────────────────────────────────
for i in $(seq 1 15); do
    sleep 1
    if curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1; then
        green "Miser ready on http://localhost:$PORT"
        green "  Log: $LOGFILE  |  PID: $(cat $PIDFILE)"
        exit 0
    fi
done

red "Miser failed to start — check $LOGFILE"
exit 1
