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
3. **Independent infrastructure**: Each plugin manages its own dependencies, servers, and build artifacts independently. No shared MCP servers.
4. **No shared MCP servers**: Each plugin declares its own MCP servers in its own `.mcp.json`.
5. **Independent versioning**: Each plugin has its own version in its marketplace entry. Plugins do not share version numbers.

### Naming conventions
- Plugin directory: `plugins/<kebab-case-name>/` (e.g., `plugins/pddl-solver/`)
- MCP server name: descriptive, kebab-case (e.g., `pddl-solver`)
- Skill names: kebab-case (e.g., `pddl-planning`, `pddl-validation`)

### Scope boundaries
- **Root `.claude/`**: Development-only tooling (agents, skills, rules). NEVER installed by end users.
- **Root `.claude-plugin/`**: Marketplace catalog. Declares which plugins exist.
- **Root `CLAUDE.md`**: Marketplace-level instructions for Claude. Describes overall structure.
- **`plugins/<name>/CLAUDE.md`**: Plugin-specific enforcement rules. Loaded when that plugin is active.
- **`plugins/<name>/skills/`**: User-facing skills. Appear as `/commands` for end users.
- **`plugins/<name>/.claude/settings.json`**: Pre-approved permissions for that plugin's tools.

### Adding a new plugin checklist

Full step-by-step guide: [docs/contributing.md](../../docs/contributing.md#creating-a-new-plugin)

Enforcement points (agent must verify all):
1. Plugin is fully self-contained under `plugins/<name>/`
2. Has `.mcp.json` (with `${CLAUDE_PLUGIN_ROOT}`), `CLAUDE.md`, `.claude/settings.json`, at least one skill
3. Registered in both `.claude-plugin/marketplace.json` and `.cursor-plugin/marketplace.json`
4. Architecture tier is the simplest possible (Tier 1 preferred)

### marketplace.json maintenance
- Every plugin must have an entry in both `.claude-plugin/marketplace.json` and `.cursor-plugin/marketplace.json`
- The `source` field must match the plugin directory path exactly
- Version bumps in marketplace.json must match actual plugin changes
