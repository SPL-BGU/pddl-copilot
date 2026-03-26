#!/usr/bin/env bash
# install_marketplace.sh — Configure all marketplace plugins for Cursor and Antigravity.
#
# Auto-discovers plugins by scanning plugins/*/.mcp.json.
# Generates MCP configs and symlinks skills for the target tools.
#
# Usage:
#   bash install_marketplace.sh                     # print configs for all detected tools
#   bash install_marketplace.sh --tool cursor       # print Cursor config only
#   bash install_marketplace.sh --tool antigravity  # print Antigravity config only
#   bash install_marketplace.sh --install           # write configs + symlink skills (with confirmation)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGINS_DIR="$REPO_ROOT/plugins"

# ── Config paths ─────────────────────────────────────────────────────────────

CURSOR_MCP="$HOME/.cursor/mcp.json"
CURSOR_SKILLS="$HOME/.cursor/skills"
ANTIGRAVITY_MCP="$HOME/.gemini/antigravity/mcp_config.json"
ANTIGRAVITY_SKILLS="$HOME/.gemini/antigravity/skills"

# ── Discover plugins ─────────────────────────────────────────────────────────

declare -a PLUGIN_NAMES=()
declare -a PLUGIN_PATHS=()

for plugin_dir in "$PLUGINS_DIR"/*/; do
    if [ -f "${plugin_dir}.mcp.json" ]; then
        PLUGIN_NAMES+=("$(basename "$plugin_dir")")
        PLUGIN_PATHS+=("$plugin_dir")
    fi
done

if [ ${#PLUGIN_NAMES[@]} -eq 0 ]; then
    echo "No plugins found in $PLUGINS_DIR (looking for .mcp.json files)." >&2
    exit 1
fi

# ── Parse MCP servers from all plugins ───────────────────────────────────────

# Build combined MCP JSON from all discovered plugins
build_combined_mcp_simple() {
    if ! command -v python3 &>/dev/null; then
        echo "python3 is required." >&2
        exit 1
    fi

    # Collect all plugin .mcp.json paths and resolve them
    local mcp_files=()
    local plugin_paths_clean=()
    for i in "${!PLUGIN_NAMES[@]}"; do
        mcp_files+=("${PLUGIN_PATHS[$i]}.mcp.json")
        plugin_paths_clean+=("${PLUGIN_PATHS[$i]%/}")
    done

    python3 -c "
import json, sys, os

mcp_files = sys.argv[1].split('|')
plugin_paths = sys.argv[2].split('|')
combined = {'mcpServers': {}}

for mcp_file, plugin_path in zip(mcp_files, plugin_paths):
    with open(mcp_file) as f:
        mcp = json.load(f)
    for server_name, config in mcp.get('mcpServers', {}).items():
        args = [a.replace('\${CLAUDE_PLUGIN_ROOT}', plugin_path) for a in config.get('args', [])]
        combined['mcpServers'][server_name] = {
            'command': config.get('command', 'bash'),
            'args': args
        }

print(json.dumps(combined, indent=2))
" "$(IFS='|'; echo "${mcp_files[*]}")" "$(IFS='|'; echo "${plugin_paths_clean[*]}")"
}

# ── Collect all skills ───────────────────────────────────────────────────────

collect_skills() {
    for i in "${!PLUGIN_PATHS[@]}"; do
        local skills_dir="${PLUGIN_PATHS[$i]}skills"
        if [ -d "$skills_dir" ]; then
            for skill_dir in "$skills_dir"/*/; do
                if [ -d "$skill_dir" ]; then
                    echo "$skill_dir"
                fi
            done
        fi
    done
}

# ── Symlink commands ─────────────────────────────────────────────────────────

print_symlink_commands() {
    local target_dir="$1"
    while IFS= read -r skill_dir; do
        local name
        name=$(basename "$skill_dir")
        echo "  ln -sfn \"${skill_dir%/}\" \"$target_dir/$name\""
    done < <(collect_skills)
}

# ── Print helpers ────────────────────────────────────────────────────────────

print_cursor() {
    echo "=== Cursor ==="
    echo "MCP config — add to ~/.cursor/mcp.json (global) or .cursor/mcp.json (project):"
    echo ""
    build_combined_mcp_simple
    echo ""
    echo "Skills — symlink to ~/.cursor/skills/:"
    print_symlink_commands "$CURSOR_SKILLS"
    echo ""
}

print_antigravity() {
    echo "=== Antigravity ==="
    echo "MCP config — add to ~/.gemini/antigravity/mcp_config.json:"
    echo ""
    build_combined_mcp_simple
    echo ""
    echo "Skills — symlink to ~/.gemini/antigravity/skills/:"
    print_symlink_commands "$ANTIGRAVITY_SKILLS"
    echo ""
}

# ── Install helpers ──────────────────────────────────────────────────────────

merge_mcp_config() {
    local target="$1"

    if [ ! -f "$target" ]; then
        mkdir -p "$(dirname "$target")"
        build_combined_mcp_simple > "$target"
        echo "  Created $target"
        return
    fi

    if ! command -v python3 &>/dev/null; then
        echo "  Cannot auto-merge into $target (python3 required). Add manually:"
        build_combined_mcp_simple
        return
    fi

    # Merge all plugin servers into the existing config
    for i in "${!PLUGIN_PATHS[@]}"; do
        local plugin_path="${PLUGIN_PATHS[$i]}"
        local mcp_file="${plugin_path}.mcp.json"

        python3 -c "
import json, sys, os

target_file = sys.argv[1]
plugin_path = sys.argv[2].rstrip('/')
mcp_file = sys.argv[3]

with open(target_file) as f:
    existing = json.load(f)

with open(mcp_file) as f:
    plugin_mcp = json.load(f)

for server_name, config in plugin_mcp.get('mcpServers', {}).items():
    if server_name in existing.get('mcpServers', {}):
        continue
    args = [a.replace('\${CLAUDE_PLUGIN_ROOT}', plugin_path) for a in config.get('args', [])]
    existing.setdefault('mcpServers', {})[server_name] = {
        'command': config.get('command', 'bash'),
        'args': args
    }

with open(target_file, 'w') as f:
    json.dump(existing, f, indent=2)
    f.write('\n')
" "$target" "$plugin_path" "$mcp_file"
    done
    echo "  Updated $target"
}

symlink_skills() {
    local target_dir="$1"
    mkdir -p "$target_dir"
    while IFS= read -r skill_dir; do
        local name
        name=$(basename "$skill_dir")
        ln -sfn "${skill_dir%/}" "$target_dir/$name"
        echo "  Linked $target_dir/$name"
    done < <(collect_skills)
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
    echo "Done. Restart your IDE to pick up the new MCP servers and skills."
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
            echo "Usage: bash install_marketplace.sh [--tool cursor|antigravity] [--install]"
            echo ""
            echo "  --tool <name>  Print config for a specific tool only"
            echo "  --install      Write MCP configs + symlink skills to detected tools"
            echo "  --help         Show this help"
            echo ""
            echo "Discovered plugins:"
            for name in "${PLUGIN_NAMES[@]}"; do
                echo "  - $name"
            done
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

echo "PDDL Copilot Marketplace — Multi-Provider Setup"
echo "Plugins discovered: ${PLUGIN_NAMES[*]}"
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
