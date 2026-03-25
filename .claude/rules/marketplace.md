---
description: Marketplace structure rules — plugin isolation, naming, and scope boundaries
paths:
  - "plugins/**"
  - ".claude-plugin/**"
  - "CLAUDE.md"
  - "README.md"
---

## Marketplace Structure Rules

### Plugin isolation (CRITICAL)
1. **Self-contained plugins**: Each plugin under `plugins/<name>/` must be fully self-contained. It must work when installed standalone via `claude plugin add`.
2. **No cross-plugin imports**: Plugin A must never reference files from Plugin B. No shared code between plugins.
3. **Independent infrastructure**: Each plugin manages its own dependencies, servers, and build artifacts independently. No shared MCP servers, no shared containers.
4. **No shared MCP servers**: Each plugin declares its own MCP servers in its own `.mcp.json`.
5. **Independent versioning**: Each plugin has its own version in its marketplace entry. Plugins do not share version numbers.

### Naming conventions
- Plugin directory: `plugins/<kebab-case-name>/` (e.g., `plugins/pddl-planning-copilot/`)
- MCP server name: descriptive, kebab-case (e.g., `pddl-planner`)
- Skill names: kebab-case (e.g., `pddl-planning`, `pddl-validation`)

### Scope boundaries
- **Root `.claude/`**: Development-only tooling (agents, skills, rules). NEVER installed by end users.
- **Root `.claude-plugin/`**: Marketplace catalog. Declares which plugins exist.
- **Root `CLAUDE.md`**: Marketplace-level instructions for Claude. Describes overall structure.
- **`plugins/<name>/CLAUDE.md`**: Plugin-specific enforcement rules. Loaded when that plugin is active.
- **`plugins/<name>/skills/`**: User-facing skills. Appear as `/commands` for end users.
- **`plugins/<name>/.claude/settings.json`**: Pre-approved permissions for that plugin's tools.

### Adding a new plugin checklist
1. Create `plugins/<name>/` directory
2. Determine the architecture tier (see `.claude/rules/plugin-development.md`): Tier 1 (pure script), Tier 2 (system deps), or Tier 3 (Docker — only if binaries require compilation)
3. Create `.mcp.json` with MCP server definition using `${CLAUDE_PLUGIN_ROOT}` for paths
4. Create `CLAUDE.md` with enforcement rules
5. Create `.claude/settings.json` with tool permissions
6. Create `scripts/launch-server.sh` appropriate for the chosen tier
7. Create the MCP server script (Python/Node)
8. **(Tier 3 only)** Create `docker/Dockerfile` and `docker/verify.sh`
9. Create a verification/test script that exercises all MCP tools
10. Create at least one skill under `skills/`
11. Add entry to `.claude-plugin/marketplace.json`
12. Update root `README.md` available plugins section

### marketplace.json maintenance
- Every plugin must have an entry in `.claude-plugin/marketplace.json`
- The `source` field must match the plugin directory path exactly
- Version bumps in marketplace.json must match actual plugin changes
