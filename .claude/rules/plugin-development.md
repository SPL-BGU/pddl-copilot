---
description: Plugin development guidelines — architecture tiers, MCP servers, skills, and verification
paths:
  - "plugins/**"
---

## Plugin Development Guidelines

### Architecture tiers — simplest first

Choose the simplest tier that works. **Docker is a last resort**, not the default.

**Tier 1 — Pure script (preferred)**
The MCP server is a Python/Node script with only pip/npm-installable dependencies. No Docker, no compiled binaries.
- Launch: `exec python3 server.py` or `exec node server.js`
- Deps: installed via `pip install` or `npm install` in the launch script or a venv
- Example: an MCP server that wraps a Python library or calls a web API

**Tier 2 — System dependencies**
The MCP server wraps tools installable via package managers (brew, apt, cargo, etc.).
- Launch: check deps → install if missing → `exec` server
- Example: an MCP server that wraps a CLI tool available via Homebrew

**Tier 3 — Docker (only when necessary)**
The MCP server wraps binaries that must be compiled from source or require an isolated environment with no native alternative.
- Launch: Docker pull/build → `exec docker run`
- Example: `plugins/pddl-planning-copilot/` wraps Fast Downward, Metric-FF, VAL (C++ binaries requiring compilation)

**When is Docker justified?**
- The tool requires compiling C/C++/Rust from source with specific build flags
- The tool has complex system dependencies not available via package managers
- The tool requires a specific OS environment (e.g., Linux-only binaries on macOS)
- If the tool is `pip install`-able, `npm install`-able, or `brew install`-able — do NOT use Docker

### MCP server patterns (all tiers)
1. **Use FastMCP**: All MCP servers use `from mcp.server.fastmcp import FastMCP`. Do not implement the MCP protocol manually.
2. **Content-or-path inputs**: Tools that accept file content should also accept file paths. See `plugins/pddl-planning-copilot/docker/solvers_server_wrapper.py` for the `_ensure_file()` pattern.
3. **Stateless tools**: Each tool invocation should be independent. Use temp directories for intermediate files, clean up after.
4. **Error dicts**: Return `{"error": True, "message": "..."}` for recoverable errors. Raise exceptions only for bugs.
5. **Timeout handling**: Wrap subprocess calls with `timeout` parameter. Return error dict on timeout, do not crash.
6. **Path translation (Tier 3 only)**: Docker plugins use `HOST_PWD` environment variable to translate between host and container paths. Tier 1-2 plugins run natively and do not need path translation.

### Skill conventions
1. **YAML frontmatter**: Every SKILL.md must have `name` and `description` in frontmatter.
2. **Activation triggers**: The `description` field should list when the skill activates (what user phrases trigger it).
3. **Mandatory rules first**: Lead with rules the agent MUST follow (bold, all-caps "MUST", "NEVER", "ALWAYS").
4. **Tool documentation**: List all available MCP tools with parameters and return types.
5. **Error handling guidance**: Tell the agent what to do when tools fail (report verbatim, never invent fallback).

### Verification requirements
1. **Every plugin must have a test/verify script**: Smoke tests for all MCP tools.
   - Tier 1-2: a test script that starts the server and exercises each tool
   - Tier 3: `docker/verify.sh` that runs tests in isolated containers
2. **Test every declared tool**: If `.mcp.json` exposes 5 tools, the verify script must test all 5.
3. **Inline test data**: Do not depend on external fixture files. Define test data in the verify script.
4. **Run verification before committing server changes**: This is the equivalent of "tests must pass".

### Launch script patterns

**Tier 1 (pure script):**
1. Ensure deps are installed (venv, pip install, npm install)
2. `exec python3 "${SCRIPT_DIR}/server.py"` or `exec node "${SCRIPT_DIR}/server.js"`

**Tier 2 (system deps):**
1. Check required tools are installed (`command -v <tool>`)
2. Suggest install command if missing (e.g., `brew install <tool>`)
3. `exec python3 "${SCRIPT_DIR}/server.py"`

**Tier 3 (Docker):**
1. Verify Docker is installed and daemon is running
2. Handle Docker Desktop slow startup (wait loop with timeout)
3. Try pulling pre-built image from GHCR before falling back to local build
4. `exec docker run --rm -i -v $HOME:/workspace -e HOST_PWD=$HOME <image> python3 -m <server_module>`
5. Use `--rm` flag so containers are removed on exit

### Docker patterns (Tier 3 only)
These apply only when Docker is justified per the architecture tier criteria above:
1. **Multi-stage builds**: Builder stage for compilation, slim runtime stage. Copy only what is needed.
2. **Strip binaries**: Always `strip --strip-unneeded` compiled binaries in the builder stage.
3. **Minimal runtime**: Install only what the MCP server needs (`pip install mcp` or equivalent).
4. **Verify imports**: Add `RUN python3 -c "from <module> import ..."` to catch import errors at build time.
5. **GHCR publishing**: Images go to `ghcr.io/<org>/<image-name>:latest`. Packages must have public visibility.
6. **Content-hash versioning**: Local builds should hash the Dockerfile + server wrapper to create version tags, avoiding unnecessary rebuilds.
