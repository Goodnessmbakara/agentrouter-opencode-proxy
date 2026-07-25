#!/usr/bin/env bash
# Start the AgentRouter local proxy.
# Reads the API key from ~/.config/opencode/api_keys/AGENT_ROUTER_API_KEY automatically.
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$DIR/.venv" ]; then
    echo "Creating virtualenv..."
    python3 -m venv "$DIR/.venv"
    "$DIR/.venv/bin/pip" install -q fastapi "uvicorn[standard]" httpx anthropic
fi

exec "$DIR/.venv/bin/python" "$DIR/proxy.py"
