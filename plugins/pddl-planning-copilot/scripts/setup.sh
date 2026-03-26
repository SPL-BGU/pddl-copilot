#!/usr/bin/env bash
# setup.sh — Configure MCP server + skills for Cursor and Antigravity.
#
# Usage:
#   bash setup.sh                     # print configs for all detected tools
#   bash setup.sh --tool cursor       # print Cursor config only
#   bash setup.sh --tool antigravity  # print Antigravity config only
#   bash setup.sh --install           # write configs + symlink skills (with confirmation)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MCP_JSON="$PLUGIN_ROOT/.mcp.json"
LAUNCH_SCRIPT="$SCRIPT_DIR/launch-server.sh"
SKILLS_DIR="$PLUGIN_ROOT/skills"

# ── Parse .mcp.json ──────────────────────────────────────────────────────────

if [ ! -f "$MCP_JSON" ]; then
    echo "Error: .mcp.json not found at $MCP_JSON" >&2
    exit 1
fi

if command -v python3 &>/dev/null; then
    SERVER_NAME=$(python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
print(list(d.get('mcpServers', {}).keys())[0])
" "$MCP_JSON")
else
    SERVER_NAME=$(grep -A1 '"mcpServers"' "$MCP_JSON" | grep '"' | head -1 | sed 's/.*"\([^"]*\)".*/\1/')
fi

if [ -z "$SERVER_NAME" ]; then
    echo "Error: Could not extract server name from $MCP_JSON" >&2
    exit 1
fi

# ── Config paths ─────────────────────────────────────────────────────────────

CURSOR_MCP="$HOME/.cursor/mcp.json"
CURSOR_SKILLS="$HOME/.cursor/skills"
ANTIGRAVITY_MCP="$HOME/.gemini/antigravity/mcp_config.json"
ANTIGRAVITY_SKILLS="$HOME/.gemini/antigravity/skills"

# ── Config generator (shared JSON format) ────────────────────────────────────

mcp_json() {
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

# ── Symlink commands ─────────────────────────────────────────────────────────

symlink_commands() {
    local target_dir="$1"
    for skill_dir in "$SKILLS_DIR"/*/; do
        local name
        name=$(basename "$skill_dir")
        echo "  ln -sfn \"$skill_dir\" \"$target_dir/$name\""
    done
}

# ── Print helpers ────────────────────────────────────────────────────────────

print_cursor() {
    echo "=== Cursor ==="
    echo "MCP config — add to ~/.cursor/mcp.json (global) or .cursor/mcp.json (project):"
    echo ""
    mcp_json
    echo ""
    echo "Skills — symlink to ~/.cursor/skills/:"
    symlink_commands "$CURSOR_SKILLS"
    echo ""
}

print_antigravity() {
    echo "=== Antigravity ==="
    echo "MCP config — add to ~/.gemini/antigravity/mcp_config.json:"
    echo ""
    mcp_json
    echo ""
    echo "Skills — symlink to ~/.gemini/antigravity/skills/:"
    symlink_commands "$ANTIGRAVITY_SKILLS"
    echo ""
}

# ── Install helpers ──────────────────────────────────────────────────────────

merge_mcp_config() {
    local target="$1"
    if [ ! -f "$target" ]; then
        mkdir -p "$(dirname "$target")"
        mcp_json > "$target"
        echo "  Created $target"
        return
    fi

    if grep -q "\"$SERVER_NAME\"" "$target" 2>/dev/null; then
        echo "  $target already contains \"$SERVER_NAME\" — skipping"
        return
    fi

    if ! command -v python3 &>/dev/null; then
        echo "  Cannot auto-merge into $target (python3 required). Add manually:"
        mcp_json
        return
    fi

    python3 -c "
import json, sys
target, server_name, launch_script = sys.argv[1], sys.argv[2], sys.argv[3]
with open(target) as f:
    existing = json.load(f)
existing.setdefault('mcpServers', {})[server_name] = {
    'command': 'bash',
    'args': [launch_script]
}
with open(target, 'w') as f:
    json.dump(existing, f, indent=2)
    f.write('\n')
" "$target" "$SERVER_NAME" "$LAUNCH_SCRIPT"
    echo "  Updated $target"
}

symlink_skills() {
    local target_dir="$1"
    mkdir -p "$target_dir"
    for skill_dir in "$SKILLS_DIR"/*/; do
        local name
        name=$(basename "$skill_dir")
        ln -sfn "$skill_dir" "$target_dir/$name"
        echo "  Linked $target_dir/$name"
    done
}

install_configs() {
    echo "This will write MCP configs and symlink skills to detected tools."
    echo ""

    local found=false

    if [ -d "$HOME/.cursor" ]; then
        found=true
        echo "  Cursor detected (~/.cursor/)"
    fi

    if [ -d "$HOME/.gemini" ]; then
        found=true
        echo "  Antigravity detected (~/.gemini/)"
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
        echo "Cursor:"
        merge_mcp_config "$CURSOR_MCP"
        symlink_skills "$CURSOR_SKILLS"
    fi

    if [ -d "$HOME/.gemini" ]; then
        echo "Antigravity:"
        merge_mcp_config "$ANTIGRAVITY_MCP"
        symlink_skills "$ANTIGRAVITY_SKILLS"
    fi

    echo ""
    echo "Done. Restart your IDE to pick up the new MCP server and skills."
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
            echo "Usage: bash setup.sh [--tool cursor|antigravity] [--install]"
            echo ""
            echo "  --tool <name>  Print config for a specific tool only"
            echo "  --install      Write MCP configs + symlink skills to detected tools"
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
echo "Skills: $SKILLS_DIR"
echo ""

if [ "$INSTALL" = true ]; then
    install_configs
    exit 0
fi

if [ -n "$TOOL" ]; then
    case "$TOOL" in
        cursor)       print_cursor ;;
        antigravity)  print_antigravity ;;
        *)
            echo "Unknown tool: $TOOL" >&2
            echo "Supported: cursor, antigravity" >&2
            exit 1
            ;;
    esac
    exit 0
fi

# No --tool flag: print all
print_cursor
print_antigravity
