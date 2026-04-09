# Architecture

## Two-Tier Skill System

This repo has two kinds of skills. They must NEVER be mixed.

- **User-facing skills** — located in `plugins/<plugin-name>/skills/`. Installed by end-users. Define how an AI agent should use the plugin's tools.
- **Development skills** — located in `.claude/skills/`. Used only by developers working on this repository. Never installed by end-users. Never placed inside `plugins/`. See `CLAUDE.md` for the current list.

## Architecture Tiers

Choose the simplest tier that works. All current plugins are Tier 1.

### Tier 1 — Pure script (preferred)

The MCP server is a Python/Node script with only pip/npm-installable dependencies.

- **Launch**: `exec python3 server.py` or `exec node server.js`
- **Deps**: installed via `pip install` or `npm install` in the launch script or a venv
- **Example**: an MCP server that wraps a Python library or calls a web API

### Tier 2 — System dependencies

The MCP server wraps tools installable via package managers (brew, apt, cargo, etc.).

- **Launch**: check deps → install if missing → `exec` server
- **Example**: an MCP server that wraps a CLI tool available via Homebrew

## MCP Server Patterns

All tiers follow these patterns:

1. **Use FastMCP**: All MCP servers use `from mcp.server.fastmcp import FastMCP`. Do not implement the MCP protocol manually.
2. **Content-or-path inputs**: Tools that accept file content should also accept file paths. See `plugins/pddl-solver/server/solver_server.py` for the `_ensure_file()` pattern.
3. **Stateless tools**: Each tool invocation should be independent. Use temp directories for intermediate files, clean up after.
4. **Error dicts**: Return `{"error": True, "message": "..."}` for recoverable errors. Raise exceptions only for bugs.
5. **Timeout handling**: Wrap subprocess calls with `timeout` parameter. Return error dict on timeout, do not crash.

## Launch Script Patterns

### Tier 1 (pure script)

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure deps
if [ ! -d "${SCRIPT_DIR}/../.venv" ]; then
  python3 -m venv "${SCRIPT_DIR}/../.venv"
  "${SCRIPT_DIR}/../.venv/bin/pip" install -r "${SCRIPT_DIR}/../requirements.txt"
fi

exec "${SCRIPT_DIR}/../.venv/bin/python3" "${SCRIPT_DIR}/../server/server.py"
```

### Tier 2 (system deps)

Same as Tier 1, but replace venv setup with a `command -v <tool>` check and `exit 1` if missing.

### CI/CD

**Integration tests** (`integration.yml`): Runs on every PR targeting `main`. Tests all plugins natively. See [contributing.md](contributing.md#verification) for the full test suite.

## Skill Conventions

1. **YAML frontmatter**: Every `SKILL.md` must have `name` and `description` in frontmatter.
2. **Activation triggers**: The `description` field should list when the skill activates (what user phrases trigger it).
3. **Mandatory rules first**: Lead with rules the agent MUST follow (bold, all-caps "MUST", "NEVER", "ALWAYS").
4. **Tool documentation**: List all available MCP tools with parameters and return types.
5. **Error handling guidance**: Tell the agent what to do when tools fail (report verbatim, never invent fallback).

## Code Conventions

- **Shell scripts**: Use `set -euo pipefail`. Quote variables. Use `${BASH_SOURCE[0]}` for script paths.
- **Python (MCP servers)**: Use FastMCP. Follow content-or-path pattern. Stateless tool functions.
- **Line endings**: Enforced via `.gitattributes` — LF for all source files.
