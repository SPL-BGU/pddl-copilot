#!/usr/bin/env bash
# static_checks.sh — Fast static validation of plugin structure and configuration.
# No Docker required. Catches broken JSON, missing files, stale settings, etc.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
FAILURES=0

ERRLOG=$(mktemp)
trap 'rm -f "$ERRLOG"' EXIT

pass() { echo -e "  ${GREEN}OK${NC}  $1"; }
fail() { echo -e "  ${RED}FAIL${NC} $1"; FAILURES=$((FAILURES + 1)); }

echo "=== Static Checks ==="
echo ""

# ---------------------------------------------------------------------------
# 1. Marketplace JSON files parse correctly
# ---------------------------------------------------------------------------
echo "--- JSON validity ---"
for f in "$REPO_ROOT"/.claude-plugin/marketplace.json \
         "$REPO_ROOT"/.cursor-plugin/marketplace.json; do
    label="${f#$REPO_ROOT/}"
    if python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$f" 2>/dev/null; then
        pass "$label"
    else
        fail "$label — invalid JSON"
    fi
done

# ---------------------------------------------------------------------------
# 2. Every plugin listed in marketplace.json has a matching directory
# ---------------------------------------------------------------------------
echo ""
echo "--- Marketplace ↔ plugin directories ---"
for marketplace in "$REPO_ROOT"/.claude-plugin/marketplace.json \
                   "$REPO_ROOT"/.cursor-plugin/marketplace.json; do
    label="${marketplace#$REPO_ROOT/}"
    plugin_sources=$(python3 -c "
import json, sys
data = json.load(open(sys.argv[1]))
for p in data.get('plugins', []):
    print(p['source'])
" "$marketplace")
    while IFS= read -r src; do
        dir="$REPO_ROOT/${src#./}"
        if [ -d "$dir" ]; then
            pass "$label → $src exists"
        else
            fail "$label → $src directory missing"
        fi
    done <<< "$plugin_sources"
done

# ---------------------------------------------------------------------------
# 3. Each plugin has required files
# ---------------------------------------------------------------------------
echo ""
echo "--- Plugin required files ---"
for plugin_dir in "$REPO_ROOT"/plugins/*/; do
    plugin_name="$(basename "$plugin_dir")"
    # CLAUDE.md is mandatory for every plugin
    if [ -f "$plugin_dir/CLAUDE.md" ]; then
        pass "$plugin_name/CLAUDE.md"
    else
        fail "$plugin_name/CLAUDE.md missing"
    fi
    # .mcp.json is required only for plugins that expose MCP tools.
    # Skills-only plugins (skills/ present, no .mcp.json) are valid.
    if [ ! -f "$plugin_dir/.mcp.json" ] && [ ! -d "$plugin_dir/skills" ]; then
        fail "$plugin_name has neither .mcp.json nor skills/ — not a valid plugin"
    fi
    # .mcp.json must be valid JSON
    if [ -f "$plugin_dir/.mcp.json" ]; then
        if python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$plugin_dir/.mcp.json" 2>/dev/null; then
            pass "$plugin_name/.mcp.json valid JSON"
        else
            fail "$plugin_name/.mcp.json invalid JSON"
        fi
        # MCP plugins must ship pre-approved permissions
        # (see .claude/rules/marketplace.md#adding-a-new-plugin-checklist)
        if [ -f "$plugin_dir/.claude/settings.json" ]; then
            pass "$plugin_name/.claude/settings.json present"
        else
            fail "$plugin_name has .mcp.json but missing .claude/settings.json"
        fi
    fi
    # settings.json must be valid JSON if it exists
    settings="$plugin_dir/.claude/settings.json"
    if [ -f "$settings" ]; then
        if python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$settings" 2>/dev/null; then
            pass "$plugin_name/.claude/settings.json valid JSON"
        else
            fail "$plugin_name/.claude/settings.json invalid JSON"
        fi
    fi
done

# ---------------------------------------------------------------------------
# 4. .mcp.json launch scripts exist
# ---------------------------------------------------------------------------
echo ""
echo "--- Launch script existence ---"
for plugin_dir in "$REPO_ROOT"/plugins/*/; do
    plugin_name="$(basename "$plugin_dir")"
    mcp_json="$plugin_dir/.mcp.json"
    [ -f "$mcp_json" ] || continue

    # Extract script paths from args arrays (replace ${CLAUDE_PLUGIN_ROOT} with plugin dir)
    scripts=$(python3 -c "
import json, sys, os
data = json.load(open(sys.argv[1]))
plugin_dir = sys.argv[2]
for srv in data.get('mcpServers', {}).values():
    for arg in srv.get('args', []):
        resolved = arg.replace('\${CLAUDE_PLUGIN_ROOT}', plugin_dir)
        if resolved.endswith('.sh') or resolved.endswith('.py'):
            print(resolved)
" "$mcp_json" "$plugin_dir")
    while IFS= read -r script; do
        [ -z "$script" ] && continue
        if [ -f "$script" ]; then
            pass "$plugin_name launch script: $(basename "$script")"
        else
            fail "$plugin_name launch script missing: $script"
        fi
    done <<< "$scripts"
done

# ---------------------------------------------------------------------------
# 5. Python server files compile
# ---------------------------------------------------------------------------
echo ""
echo "--- Python syntax ---"
for server_py in "$REPO_ROOT"/plugins/*/server/*.py; do
    label="${server_py#$REPO_ROOT/}"
    if python3 -m py_compile "$server_py" 2>"$ERRLOG"; then
        pass "$label"
    else
        fail "$label — syntax error"
        cat "$ERRLOG" >&2
    fi
done

# ---------------------------------------------------------------------------
# 6. settings.json tool names match server @mcp.tool functions
# ---------------------------------------------------------------------------
echo ""
echo "--- Settings ↔ server tool consistency ---"
for plugin_dir in "$REPO_ROOT"/plugins/*/; do
    plugin_name="$(basename "$plugin_dir")"
    settings="$plugin_dir/.claude/settings.json"
    mcp_json="$plugin_dir/.mcp.json"
    [ -f "$settings" ] && [ -f "$mcp_json" ] || continue

    # Get the MCP server name from .mcp.json
    server_name=$(python3 -c "
import json, sys
data = json.load(open(sys.argv[1]))
for name in data.get('mcpServers', {}):
    print(name)
    break
" "$mcp_json")

    # Get tool names from settings.json (strip mcp__<server>__ prefix)
    settings_tools=$(python3 -c "
import json, sys
data = json.load(open(sys.argv[1]))
prefix = 'mcp__' + sys.argv[2] + '__'
for tool in data.get('permissions', {}).get('allow', []):
    if tool.startswith(prefix):
        print(tool[len(prefix):])
" "$settings" "$server_name")

    # Get @mcp.tool decorated function names from server files
    # Handles both @mcp.tool() (uses function name) and @mcp.tool(name='custom')
    server_tools=$(python3 -c "
import ast, sys, os
for f in sorted(os.listdir(sys.argv[1])):
    if not f.endswith('.py'): continue
    tree = ast.parse(open(os.path.join(sys.argv[1], f)).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                src = ast.dump(dec)
                if 'mcp' in src and 'tool' in src:
                    # Check for explicit name= keyword argument
                    tool_name = node.name
                    if isinstance(dec, ast.Call):
                        for kw in dec.keywords:
                            if kw.arg == 'name' and isinstance(kw.value, ast.Constant):
                                tool_name = kw.value.value
                    print(tool_name)
" "$plugin_dir/server")

    # Compare: every settings tool should exist in server
    while IFS= read -r tool; do
        [ -z "$tool" ] && continue
        if echo "$server_tools" | grep -qx "$tool"; then
            pass "$plugin_name settings: $tool found in server"
        else
            fail "$plugin_name settings: $tool NOT found in server"
        fi
    done <<< "$settings_tools"

    # Reverse: every server tool should have a settings entry
    while IFS= read -r tool; do
        [ -z "$tool" ] && continue
        if echo "$settings_tools" | grep -qx "$tool"; then
            pass "$plugin_name server: $tool has settings entry"
        else
            fail "$plugin_name server: $tool MISSING from settings.json"
        fi
    done <<< "$server_tools"
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
if [ "$FAILURES" -gt 0 ]; then
    echo -e "${RED}${FAILURES} check(s) failed.${NC}"
    exit 1
fi
echo -e "${GREEN}All static checks passed.${NC}"
