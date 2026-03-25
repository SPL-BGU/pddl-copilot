# PDDL Copilot — Plugin Marketplace

This repository is a Claude Code plugin marketplace. Each plugin lives in its own subdirectory under `plugins/`.

## Structure

- `.claude-plugin/marketplace.json` — marketplace catalog listing all available plugins
- `.claude-plugin/plugin.json` — marketplace-level metadata
- `plugins/<plugin-name>/` — each plugin with its own `CLAUDE.md`, `.mcp.json`, skills, scripts, etc.

## Available Plugins

- **pddl-planning-copilot** (`plugins/pddl-planning-copilot/`) — PDDL planning, validation, and simulation using Fast Downward, Metric-FF, and VAL in Docker

## Adding a New Plugin

1. Create a directory under `plugins/<your-plugin-name>/`
2. Add the required plugin files: `.mcp.json`, `CLAUDE.md`, `.claude/settings.json`, and any skills/scripts
3. Add an entry to `.claude-plugin/marketplace.json` in the `plugins` array with `"source": "plugins/<your-plugin-name>"`
