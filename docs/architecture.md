# Architecture

## Two-Tier Skill System

This repo has two kinds of skills. They must NEVER be mixed.

- **User-facing skills** — located in `plugins/<plugin-name>/skills/`. Installed by end-users. Define how an AI agent should use the plugin's tools.
- **Development skills** — located in `.claude/skills/`. Used only by developers working on this repository. Never installed by end-users. Never placed inside `plugins/`. See `CLAUDE.md` for the current list.

## Architecture Tiers

Choose the simplest tier that works. Docker is a last resort, not the default.

### Tier 1 — Pure script (preferred)

The MCP server is a Python/Node script with only pip/npm-installable dependencies. No Docker, no compiled binaries.

- **Launch**: `exec python3 server.py` or `exec node server.js`
- **Deps**: installed via `pip install` or `npm install` in the launch script or a venv
- **Example**: an MCP server that wraps a Python library or calls a web API

### Tier 2 — System dependencies

The MCP server wraps tools installable via package managers (brew, apt, cargo, etc.).

- **Launch**: check deps → install if missing → `exec` server
- **Example**: an MCP server that wraps a CLI tool available via Homebrew

### Tier 3 — Docker (only when necessary)

The MCP server wraps binaries that must be compiled from source or require an isolated environment with no native alternative.

- **Launch**: Docker pull/build → `exec docker run`
- **Example**: `plugins/pddl-solver/` and `plugins/pddl-validator/` wrap Fast Downward, Metric-FF, VAL (C++ binaries requiring compilation)

### When is Docker justified?

- The tool requires compiling C/C++/Rust from source with specific build flags
- The tool has complex system dependencies not available via package managers
- The tool requires a specific OS environment (e.g., Linux-only binaries on macOS)
- If the tool is `pip install`-able, `npm install`-able, or `brew install`-able — do NOT use Docker

## MCP Server Patterns

All tiers follow these patterns:

1. **Use FastMCP**: All MCP servers use `from mcp.server.fastmcp import FastMCP`. Do not implement the MCP protocol manually.
2. **Content-or-path inputs**: Tools that accept file content should also accept file paths. See `plugins/pddl-solver/server/solver_server.py` for the `_ensure_file()` pattern.
3. **Stateless tools**: Each tool invocation should be independent. Use temp directories for intermediate files, clean up after.
4. **Error dicts**: Return `{"error": True, "message": "..."}` for recoverable errors. Raise exceptions only for bugs.
5. **Timeout handling**: Wrap subprocess calls with `timeout` parameter. Return error dict on timeout, do not crash.
6. **Path translation (Tier 3 only)**: Docker plugins use `HOST_PWD` environment variable to translate between host and container paths. Tier 1-2 plugins run natively and do not need path translation.

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

### Tier 3 (Docker)

See `plugins/pddl-solver/scripts/launch-server.sh` for the reference implementation.

## Docker Patterns (Tier 3 Only)

### Build conventions

1. **Multi-stage builds**: Builder stage for compilation, slim runtime stage. Copy only what is needed.
2. **Strip binaries**: Always `strip --strip-unneeded` compiled binaries in the builder stage.
3. **Minimal runtime**: Install only what the MCP server needs (`pip install mcp` or equivalent).
4. **Verify imports**: Add `RUN python3 -c "from <module> import ..."` to catch import errors at build time.

### CI/CD

**Integration tests** (`integration.yml`): Runs on every PR targeting `main`. Tests all plugins natively (no Docker). See [contributing.md](contributing.md#verification) for the full test suite.

## Skill Conventions

1. **YAML frontmatter**: Every `SKILL.md` must have `name` and `description` in frontmatter.
2. **Activation triggers**: The `description` field should list when the skill activates (what user phrases trigger it).
3. **Mandatory rules first**: Lead with rules the agent MUST follow (bold, all-caps "MUST", "NEVER", "ALWAYS").
4. **Tool documentation**: List all available MCP tools with parameters and return types.
5. **Error handling guidance**: Tell the agent what to do when tools fail (report verbatim, never invent fallback).

## Code Conventions

- **Shell scripts**: Use `set -euo pipefail`. Quote variables. Use `${BASH_SOURCE[0]}` for script paths.
- **Python (MCP servers)**: Use FastMCP. Follow content-or-path pattern. Stateless tool functions.
- **Docker**: Multi-stage builds. Strip binaries. Minimal runtime images.
- **Line endings**: Enforced via `.gitattributes` — LF for all source files.
