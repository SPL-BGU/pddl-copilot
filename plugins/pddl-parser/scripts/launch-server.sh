#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_DIR/.venv"
SERVER="$PLUGIN_DIR/server/parser_server.py"

if [ ! -d "$VENV_DIR" ]; then
    echo "[pddl-parser] Setting up Python environment..." >&2
    if command -v uv &>/dev/null; then
        uv venv "$VENV_DIR"
        uv pip install --python "$VENV_DIR/bin/python3" -r "$PLUGIN_DIR/requirements.txt"
    else
        python3 -m venv "$VENV_DIR"
        "$VENV_DIR/bin/pip" install --quiet -r "$PLUGIN_DIR/requirements.txt"
    fi
    # Install optional dependencies (non-fatal)
    if [ -f "$PLUGIN_DIR/requirements-optional.txt" ]; then
        if command -v uv &>/dev/null; then
            uv pip install --python "$VENV_DIR/bin/python3" -r "$PLUGIN_DIR/requirements-optional.txt" 2>/dev/null || true
        else
            "$VENV_DIR/bin/pip" install --quiet -r "$PLUGIN_DIR/requirements-optional.txt" 2>/dev/null || true
        fi
    fi
    echo "[pddl-parser] Ready." >&2
fi

exec "$VENV_DIR/bin/python3" "$SERVER"
