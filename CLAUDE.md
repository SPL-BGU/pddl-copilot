# PDDL Copilot — Plugin Marketplace

This repository is a Claude Code plugin marketplace. Each plugin lives in its own subdirectory under `plugins/`.

## Structure

- `.claude-plugin/marketplace.json` — marketplace catalog listing all available plugins
- `.claude-plugin/plugin.json` — marketplace-level metadata
- `plugins/<plugin-name>/` — each plugin with its own `CLAUDE.md`, `.mcp.json`, skills, scripts, etc.
- `docker/` — shared Docker image build (Dockerfile for Fast Downward, Metric-FF, VAL)
- `install_marketplace.sh` — unified Cursor/Antigravity installer (auto-discovers all plugins)

## Available Plugins

- **pddl-solver** (`plugins/pddl-solver/`) — PDDL planning using Fast Downward and Metric-FF in Docker
- **pddl-validator** (`plugins/pddl-validator/`) — PDDL validation and state transition simulation using VAL in Docker

## Ollama MCP Bridge

`ollama_mcp_bridge.py` — root-level CLI tool that connects Ollama models to marketplace plugins via MCP. Not a plugin itself. Reads `marketplace.json` to discover plugins dynamically.

Run: `python3 ollama_mcp_bridge.py` (deps: `pip3 install -r requirements-bridge.txt`)

## Two-Tier Skill System

This repo has two kinds of skills. They must NEVER be mixed.

### User-facing skills (inside plugins)
Located in `plugins/<plugin-name>/skills/`. Installed by end-users when they add the plugin. These define how Claude should use the plugin's tools.

Examples: `/pddl-planning`, `/pddl-validation`

### Development skills (root .claude/)
Located in `.claude/skills/`. Used only by developers working on this repository. Never installed by end-users. Never placed inside `plugins/`.

Available dev skills:
- `/plan-review-simplify <task>` — 5-phase planning workflow with built-in simplification review
- `/simplify [target]` — Review code/plan for unnecessary complexity (forks to simplifier agent)
- `/debug-and-simplify <issue>` — Layer-by-layer debugging with minimal fix and simplification review
- `/plugin-specialist <question>` — Research-driven agent: fetches current plugin docs, studies real marketplace plugins, recommends architecture

## Development Workflow

### For multi-file changes or new features:
Use `/plan-review-simplify <description>` — explores existing code, plans, reviews for simplification and plugin isolation, presents for approval, then executes with verification.

### For debugging Docker/MCP/config issues:
Use `/debug-and-simplify <error or symptom>` — systematic layer-by-layer diagnosis (Docker → MCP → config → CI/CD → paths) with minimal fix.

### For plugin development guidance:
Use `/plugin-specialist <question>` — research-driven agent that fetches up-to-date Claude Code plugin docs, studies real plugins from official and community marketplaces, and recommends the simplest architecture for your use case.

### For reviewing complexity:
Use `/simplify [description]` — forks to the simplifier agent which reviews for over-engineering, isolation violations, and convention deviations.

## Verification

Each plugin has its own verify/test script. Run before committing server or infrastructure changes:

- **Tier 3 (Docker) plugins**: `bash plugins/<name>/tests/verify.sh`
- **Tier 1-2 plugins**: the plugin's test script (varies per plugin)

Examples:
```bash
bash plugins/pddl-solver/tests/verify.sh
bash plugins/pddl-validator/tests/verify.sh
```

## Adding a New Plugin

1. Create `plugins/<your-plugin-name>/` directory
2. **Choose architecture tier** (see `.claude/rules/plugin-development.md`):
   - **Tier 1** (preferred): Pure Python/Node MCP server — no Docker, just pip/npm deps
   - **Tier 2**: Wraps system-installable tools (brew/apt/cargo)
   - **Tier 3**: Docker — only when binaries must be compiled from source with no native alternative
3. Create `.mcp.json` with MCP server definition using `${CLAUDE_PLUGIN_ROOT}` for paths
4. Create `CLAUDE.md` with enforcement rules for the plugin
5. Create `.claude/settings.json` with pre-approved tool permissions
6. Create `scripts/launch-server.sh` appropriate for the chosen tier
7. Create the MCP server script
8. **(Tier 3 only)** Use the shared `docker/Dockerfile` image; create `tests/verify.sh`
9. Create a verify/test script that exercises all MCP tools
10. Create at least one skill under `skills/`
11. Add entry to `.claude-plugin/marketplace.json` and `.cursor-plugin/marketplace.json`
12. Verify auto-discovery: `bash install_marketplace.sh`
13. Update this file's Available Plugins section

Use `/plugin-specialist` to research current plugin patterns and `plugins/pddl-solver/` as a local reference (noting it is Tier 3 — most plugins should be simpler).

## Rules for Developers

- `.claude/rules/simplification.md` — Global simplification principle (minimal changes, no duplication, proportional complexity)
- `.claude/rules/marketplace.md` — Plugin isolation, naming conventions, scope boundaries
- `.claude/rules/plugin-development.md` — Docker, MCP server, skill, and verification conventions

## Code Conventions

- **Shell scripts**: Use `set -euo pipefail`. Quote variables. Use `${BASH_SOURCE[0]}` for script paths.
- **Python (MCP servers)**: Use FastMCP. Follow content-or-path pattern. Stateless tool functions.
- **Docker**: Multi-stage builds. Strip binaries. Minimal runtime images.
- **Line endings**: Enforced via `.gitattributes` — LF for all source files.
