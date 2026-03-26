#!/usr/bin/env bash
# setup.sh — Generate MCP server config for Cursor, Codex CLI, and Antigravity.
#
# Usage:
#   bash setup.sh                     # print configs for all detected tools
#   bash setup.sh --tool cursor       # print Cursor config only
#   bash setup.sh --tool codex        # print Codex CLI config only
#   bash setup.sh --tool antigravity  # print Antigravity config only
#   bash setup.sh --install           # write configs to detected tools (with confirmation)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MCP_JSON="$PLUGIN_ROOT/.mcp.json"
LAUNCH_SCRIPT="$SCRIPT_DIR/launch-server.sh"

# ── Parse .mcp.json ──────────────────────────────────────────────────────────

if [ ! -f "$MCP_JSON" ]; then
    echo "Error: .mcp.json not found at $MCP_JSON" >&2
    exit 1
fi

# Extract server name (first key under mcpServers) — pure bash + python fallback
if command -v python3 &>/dev/null; then
    SERVER_NAME=$(python3 -c "
import json, sys
with open('$MCP_JSON') as f:
    d = json.load(f)
print(list(d.get('mcpServers', {}).keys())[0])
")
else
    # Fallback: grep for first key after mcpServers
    SERVER_NAME=$(grep -A1 '"mcpServers"' "$MCP_JSON" | grep '"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/')
fi

if [ -z "$SERVER_NAME" ]; then
    echo "Error: Could not extract server name from $MCP_JSON" >&2
    exit 1
fi

# ── Config locations ─────────────────────────────────────────────────────────

CURSOR_GLOBAL="$HOME/.cursor/mcp.json"
ANTIGRAVITY_CONFIG="$HOME/.gemini/antigravity/mcp_config.json"
CODEX_CONFIG="$HOME/.codex/config.toml"

# ── Config generators ────────────────────────────────────────────────────────

json_config() {
    cat <<EOF
{
  "mcpServers": {
    "$SERVER_NAME": {
      "command": "bash",
      "args": ["$LAUNCH_SCRIPT"]
    }
  }
}
EOF
}

toml_config() {
    cat <<EOF
[mcp_servers.$SERVER_NAME]
command = "bash"
args = ["$LAUNCH_SCRIPT"]
EOF
}

codex_add_command() {
    echo "codex mcp add $SERVER_NAME -- bash $LAUNCH_SCRIPT"
}

# ── Output helpers ───────────────────────────────────────────────────────────

print_cursor() {
    echo "=== Cursor ==="
    echo "Add to .cursor/mcp.json (project-level) or ~/.cursor/mcp.json (global):"
    echo ""
    json_config
    echo ""
}

print_antigravity() {
    echo "=== Antigravity ==="
    echo "Add to ~/.gemini/antigravity/mcp_config.json:"
    echo ""
    json_config
    echo ""
}

print_codex() {
    echo "=== OpenAI Codex CLI ==="
    echo "Quick setup:"
    echo "  $(codex_add_command)"
    echo ""
    echo "Or add to ~/.codex/config.toml:"
    echo ""
    toml_config
    echo ""
}

# ── Install helper ───────────────────────────────────────────────────────────

merge_json_config() {
    local target="$1"
    if [ ! -f "$target" ]; then
        mkdir -p "$(dirname "$target")"
        json_config > "$target"
        echo "  Created $target"
        return
    fi

    # Check if server already configured
    if grep -q "\"$SERVER_NAME\"" "$target" 2>/dev/null; then
        echo "  $target already contains \"$SERVER_NAME\" — skipping (edit manually if needed)"
        return
    fi

    # Merge using python3
    if ! command -v python3 &>/dev/null; then
        echo "  Cannot auto-merge into $target (python3 required). Add manually:"
        json_config
        return
    fi

    python3 -c "
import json, sys
with open('$target') as f:
    existing = json.load(f)
existing.setdefault('mcpServers', {})['$SERVER_NAME'] = {
    'command': 'bash',
    'args': ['$LAUNCH_SCRIPT']
}
with open('$target', 'w') as f:
    json.dump(existing, f, indent=2)
    f.write('\n')
"
    echo "  Updated $target"
}

append_toml_config() {
    local target="$1"
    if [ -f "$target" ] && grep -q "\[mcp_servers\.$SERVER_NAME\]" "$target" 2>/dev/null; then
        echo "  $target already contains [$SERVER_NAME] — skipping"
        return
    fi
    mkdir -p "$(dirname "$target")"
    echo "" >> "$target"
    toml_config >> "$target"
    echo "  Updated $target"
}

install_configs() {
    echo "This will write MCP configs to detected tool config files."
    echo ""

    local found=false

    # Cursor
    if [ -d "$HOME/.cursor" ]; then
        found=true
        echo "  Cursor detected (~/.cursor/)"
    fi

    # Antigravity
    if [ -d "$HOME/.gemini" ]; then
        found=true
        echo "  Antigravity detected (~/.gemini/)"
    fi

    # Codex
    if command -v codex &>/dev/null || [ -d "$HOME/.codex" ]; then
        found=true
        echo "  Codex CLI detected"
    fi

    if [ "$found" = false ]; then
        echo "No supported tools detected. Use --tool <name> to generate configs manually."
        exit 0
    fi

    echo ""
    read -r -p "Proceed? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[Yy] ]]; then
        echo "Aborted."
        exit 0
    fi

    echo ""

    if [ -d "$HOME/.cursor" ]; then
        merge_json_config "$CURSOR_GLOBAL"
    fi

    if [ -d "$HOME/.gemini" ]; then
        merge_json_config "$ANTIGRAVITY_CONFIG"
    fi

    if command -v codex &>/dev/null || [ -d "$HOME/.codex" ]; then
        append_toml_config "$CODEX_CONFIG"
    fi

    echo ""
    echo "Done. Restart your IDE/CLI to pick up the new MCP server."
    echo ""
    echo "For best results, add the agent instructions from INSTRUCTIONS.md"
    echo "to your tool's custom rules or system prompt."
    echo "  File: $PLUGIN_ROOT/INSTRUCTIONS.md"
}

# ── Parse arguments ──────────────────────────────────────────────────────────

TOOL=""
INSTALL=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tool)
            TOOL="${2:-}"
            shift 2
            ;;
        --install)
            INSTALL=true
            shift
            ;;
        --help|-h)
            echo "Usage: bash setup.sh [--tool cursor|codex|antigravity] [--install]"
            echo ""
            echo "  --tool <name>  Print config for a specific tool only"
            echo "  --install      Write configs to detected tool config files"
            echo "  --help         Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Run with --help for usage." >&2
            exit 1
            ;;
    esac
done

# ── Main ─────────────────────────────────────────────────────────────────────

echo "PDDL Copilot — MCP Server Setup"
echo "Server: $SERVER_NAME"
echo "Launch: $LAUNCH_SCRIPT"
echo ""

if [ "$INSTALL" = true ]; then
    install_configs
    exit 0
fi

if [ -n "$TOOL" ]; then
    case "$TOOL" in
        cursor)       print_cursor ;;
        antigravity)  print_antigravity ;;
        codex)        print_codex ;;
        *)
            echo "Unknown tool: $TOOL" >&2
            echo "Supported: cursor, codex, antigravity" >&2
            exit 1
            ;;
    esac
    exit 0
fi

# No --tool flag: print all
print_cursor
print_codex
print_antigravity

echo "---"
echo "For best results, add the agent instructions from INSTRUCTIONS.md"
echo "to your tool's custom rules or system prompt."
echo "  File: $PLUGIN_ROOT/INSTRUCTIONS.md"
