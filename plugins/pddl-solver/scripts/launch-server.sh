#!/usr/bin/env bash
# launch-server.sh — Called by .mcp.json at plugin load.
#
# Creates a Python venv with unified-planning engines and runs the MCP server.
# No Docker required — planners are pip-installable.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_DIR/.venv"
SERVER="$PLUGIN_DIR/server/solver_server.py"

if [ ! -d "$VENV_DIR" ]; then
    echo "[pddl-solver] Setting up Python environment..." >&2
    if command -v uv &>/dev/null; then
        uv venv "$VENV_DIR" >&2
        uv pip install --python "$VENV_DIR/bin/python3" -r "$PLUGIN_DIR/requirements.txt" >&2
    else
        python3 -m venv "$VENV_DIR"
        "$VENV_DIR/bin/pip" install --quiet -r "$PLUGIN_DIR/requirements.txt"
    fi
    echo "[pddl-solver] Ready." >&2
fi

exec "$VENV_DIR/bin/python3" "$SERVER"
