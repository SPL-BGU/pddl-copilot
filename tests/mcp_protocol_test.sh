#!/usr/bin/env bash
# mcp_protocol_test.sh — Verify each plugin's MCP server registers all expected tools
# via the MCP stdio protocol. Catches @mcp.tool() decorator / FastMCP wiring bugs
# that direct Python imports would miss.
#
# Skills-only plugins (no .mcp.json) are skipped: there is no server to probe.
# Each per-plugin block below gates on `-f $PLUGIN_DIR/.mcp.json` before running.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
FAILURES=0

pass() { echo -e "  ${GREEN}OK${NC}  $1"; }
fail() { echo -e "  ${RED}FAIL${NC} $1"; FAILURES=$((FAILURES + 1)); }

ERRLOG=$(mktemp)
trap 'rm -f "$ERRLOG"' EXIT

echo "=== MCP Protocol Smoke Tests ==="
echo ""

# Generic MCP tools/list verification script (works both in Docker and natively)
MCP_LIST_SCRIPT='
import asyncio
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    expected = set(sys.argv[1].split(","))
    server_cmd = sys.argv[2]
    server_args = sys.argv[3:]
    params = StdioServerParameters(command=server_cmd, args=server_args)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            registered = {t.name for t in result.tools}
            print(f"Registered: {sorted(registered)}")
            missing = expected - registered
            if missing:
                print(f"MISSING: {sorted(missing)}", file=sys.stderr)
                sys.exit(1)
            print("ALL_TOOLS_OK")

asyncio.run(main())
'

# ---------------------------------------------------------------------------
# Test pddl-solver (Tier 1, native)
# ---------------------------------------------------------------------------

echo "--- pddl-solver (Tier 1) ---"
SOLVER_DIR="$REPO_ROOT/plugins/pddl-solver"
SOLVER_VENV="$SOLVER_DIR/.venv"

if [ ! -f "$SOLVER_DIR/.mcp.json" ]; then
    echo "  skipped — no .mcp.json (skills-only plugin)"
else
    # Ensure venv exists
    if [ ! -d "$SOLVER_VENV" ]; then
        echo "  Setting up solver venv..."
        if command -v uv &>/dev/null; then
            uv venv "$SOLVER_VENV"
            uv pip install --python "$SOLVER_VENV/bin/python3" -r "$SOLVER_DIR/requirements.txt"
        else
            python3 -m venv "$SOLVER_VENV"
            "$SOLVER_VENV/bin/pip" install --quiet -r "$SOLVER_DIR/requirements.txt"
        fi
    fi

    SOLVER_PYTHON="$SOLVER_VENV/bin/python3"
    echo -n "  MCP tools/list...       "
    if $SOLVER_PYTHON -c "$MCP_LIST_SCRIPT" \
        "classic_planner,numeric_planner,save_plan" \
        "$SOLVER_PYTHON" "$SOLVER_DIR/server/solver_server.py" \
        2>"$ERRLOG" | grep -q "ALL_TOOLS_OK"; then
        pass "all 3 tools registered"
    else
        fail "pddl-solver tools/list"
        cat "$ERRLOG" >&2
    fi
fi

# ---------------------------------------------------------------------------
# Test pddl-validator (Tier 1, native)
# ---------------------------------------------------------------------------

echo ""
echo "--- pddl-validator (Tier 1) ---"
VALIDATOR_DIR="$REPO_ROOT/plugins/pddl-validator"
VALIDATOR_VENV="$VALIDATOR_DIR/.venv"

if [ ! -f "$VALIDATOR_DIR/.mcp.json" ]; then
    echo "  skipped — no .mcp.json (skills-only plugin)"
else
    # Ensure venv exists
    if [ ! -d "$VALIDATOR_VENV" ]; then
        echo "  Setting up validator venv..."
        if command -v uv &>/dev/null; then
            uv venv "$VALIDATOR_VENV"
            uv pip install --python "$VALIDATOR_VENV/bin/python3" -r "$VALIDATOR_DIR/requirements.txt"
        else
            python3 -m venv "$VALIDATOR_VENV"
            "$VALIDATOR_VENV/bin/pip" install --quiet -r "$VALIDATOR_DIR/requirements.txt"
        fi
    fi

    VALIDATOR_PYTHON="$VALIDATOR_VENV/bin/python3"
    echo -n "  MCP tools/list...       "
    if $VALIDATOR_PYTHON -c "$MCP_LIST_SCRIPT" \
        "validate_pddl_syntax,get_state_transition" \
        "$VALIDATOR_PYTHON" "$VALIDATOR_DIR/server/validator_server.py" \
        2>"$ERRLOG" | grep -q "ALL_TOOLS_OK"; then
        pass "all 2 tools registered"
    else
        fail "pddl-validator tools/list"
        cat "$ERRLOG" >&2
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
if [ "$FAILURES" -gt 0 ]; then
    echo -e "${RED}${FAILURES} MCP protocol test(s) failed.${NC}"
    exit 1
fi
echo -e "${GREEN}All MCP protocol tests passed.${NC}"
