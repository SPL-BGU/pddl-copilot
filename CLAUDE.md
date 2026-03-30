# PDDL Copilot — Plugin Marketplace

This repository is a Claude Code plugin marketplace. Each plugin lives in its own subdirectory under `plugins/`.

## Structure

- `.claude-plugin/marketplace.json` — marketplace catalog listing all available plugins
- `.claude-plugin/plugin.json` — marketplace-level metadata
- `plugins/<plugin-name>/` — each plugin with its own `CLAUDE.md`, `.mcp.json`, skills, scripts, etc.
- `docker/` — shared Docker image build (Dockerfile for Fast Downward, Metric-FF, VAL)
  - **`solvers_server_wrapper.py`** is baked into the Docker image but **overridden at runtime** by each plugin's own server script (volume-mounted). Modifying the wrapper triggers a Docker image rebuild + GHCR re-push via CI. Only update it when intentionally changing the baked-in fallback — prefer editing the plugin servers (`plugins/<name>/server/`) for MCP-facing changes.
- `install_marketplace.sh` — unified Cursor/Antigravity installer (auto-discovers all plugins)

## Available Plugins

- **pddl-solver** (`plugins/pddl-solver/`) — PDDL planning using Fast Downward and Metric-FF in Docker
- **pddl-validator** (`plugins/pddl-validator/`) — PDDL validation and state transition simulation using VAL in Docker
- **pddl-parser** (`plugins/pddl-parser/`) — PDDL parsing and structured trajectory generation using pddl-plus-parser (pure Python, no Docker)

## Ollama MCP Bridge

`ollama_mcp_bridge.py` — root-level CLI tool that connects Ollama models to marketplace plugins via MCP. Not a plugin itself. Reads `marketplace.json` to discover plugins dynamically.

Run: `python3 ollama_mcp_bridge.py` (deps: `pip3 install -r requirements-bridge.txt`)

## Two-Tier Skill System

User-facing skills live in `plugins/<name>/skills/`. Dev skills live in `.claude/skills/`. They must NEVER be mixed. See [docs/architecture.md](docs/architecture.md#two-tier-skill-system) for full explanation.

Available dev skills:
- `/plan-review-simplify <task>` — 5-phase planning workflow with built-in simplification review
- `/simplify [target]` — Review code/plan for unnecessary complexity (forks to simplifier agent)
- `/debug-and-simplify <issue>` — Layer-by-layer debugging with minimal fix and simplification review
- `/plugin-specialist <question>` — Research-driven agent: fetches current plugin docs, studies real marketplace plugins, recommends architecture

## Verification

Run the affected plugin's verify script before committing server changes. CI gates PRs with static checks, plugin tests, and MCP protocol validation. See [docs/contributing.md](docs/contributing.md#verification).

Root-level `tests/` contains cross-plugin test infrastructure (static checks, MCP protocol tests). Plugin-specific tests live in `plugins/<name>/tests/`.

## Adding a New Plugin

Full guide: [docs/contributing.md](docs/contributing.md#creating-a-new-plugin)

## Rules for Developers

- `.claude/rules/simplification.md` — Global simplification principle (minimal changes, no duplication, proportional complexity)
- `.claude/rules/marketplace.md` — Plugin isolation, naming conventions, scope boundaries
- `.claude/rules/plugin-development.md` — Docker, MCP server, skill, and verification conventions

## Code Conventions

See [docs/architecture.md](docs/architecture.md#code-conventions).
