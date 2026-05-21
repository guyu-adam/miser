#!/usr/bin/env bash
# codex-miser.sh — One-shot Miser integration for Codex CLI (Agent adaptation #7)
# Usage: bash codex-miser.sh

set -e

CODEX_CONFIG="$HOME/.codex/config.toml"
MISER_PORT="${MISER_PORT:-7860}"

if ! command -v codex &>/dev/null; then
    echo "Codex CLI not found. Install from: https://github.com/openai/codex"
    exit 1
fi

mkdir -p "$(dirname "$CODEX_CONFIG")"

cat >> "$CODEX_CONFIG" << 'TOML'

# Miser — local co-processor tools
[tools.miser_read]
command = "curl"
args = ["-s", "-X", "POST", "http://localhost:${MISER_PORT}/v1/read", "-H", "Content-Type: application/json", "-d", "{\"path\":\"$1\"}"]
description = "Read a file locally (zero API tokens)"

[tools.miser_outline]
command = "curl"
args = ["-s", "-X", "POST", "http://localhost:${MISER_PORT}/v1/outline", "-H", "Content-Type: application/json", "-d", "{\"path\":\"$1\"}"]
description = "Extract function/class outline from a source file"

[tools.miser_grep]
command = "curl"
args = ["-s", "-X", "POST", "http://localhost:${MISER_PORT}/v1/grep", "-H", "Content-Type: application/json", "-d", "{\"path\":\"$1\",\"pattern\":\"$2\"}"]
description = "Search a file with regex"

[tools.miser_explain]
command = "curl"
args = ["-s", "-X", "POST", "http://localhost:${MISER_PORT}/v1/chat/completions", "-H", "Content-Type: application/json", "-d", "{\"messages\":[{\"role\":\"user\",\"content\":\"Explain: $1\"}],\"max_tokens\":300}"]
description = "Explain code using local LLM (zero API cost)"

TOML

echo "✓ Codex CLI configured with Miser tools"
echo "  Restart Codex to activate."
