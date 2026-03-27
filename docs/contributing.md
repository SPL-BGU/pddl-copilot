# Contributing to PDDL Copilot

## Prerequisites

- [Docker](https://docker.com) installed and running (required for Tier 3 plugins)
- Python 3
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (for development skills and testing)
- Git

## Development Setup

```bash
git clone https://github.com/SPL-BGU/pddl-copilot.git
cd pddl-copilot
```

To test a plugin locally without marketplace installation:

```bash
claude --plugin-dir ./plugins/pddl-solver
```

Development skills (`/plan-review-simplify`, `/simplify`, `/debug-and-simplify`, `/plugin-specialist`) are listed in the root `CLAUDE.md`.

## Creating a New Plugin

### 1. Choose an architecture tier

Default to the simplest tier that works. See [Architecture Tiers](architecture.md#architecture-tiers) for full details.

| Tier | When to use | Example |
|------|-------------|---------|
| **Tier 1** (preferred) | Tool is pip/npm-installable | Python library wrapper, web API client |
| **Tier 2** | Tool is brew/apt/cargo-installable | CLI tool wrapper |
| **Tier 3** | Tool must be compiled from source | pddl-solver, pddl-validator (C++ binaries) |

### 2. Scaffold the plugin directory

```
plugins/<your-plugin-name>/
├── .mcp.json                    # MCP server definition
├── .claude-plugin/
│   └── plugin.json              # Plugin metadata (name, version, description)
├── .claude/
│   └── settings.json            # Pre-approved tool permissions
├── CLAUDE.md                    # Plugin-specific enforcement rules
├── scripts/
│   └── launch-server.sh         # Server launch script (tier-appropriate)
├── server/
│   └── <server>.py              # MCP server implementation
├── skills/
│   └── <skill-name>/
│       └── SKILL.md             # User-facing skill definition
└── tests/
    └── verify.sh                # Smoke tests for all MCP tools
```

### 3. Create the MCP server definition

Create `.mcp.json` using `${CLAUDE_PLUGIN_ROOT}` for portable paths:

```json
{
  "mcpServers": {
    "<your-plugin-name>": {
      "command": "bash",
      "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/launch-server.sh"]
    }
  }
}
```

### 4. Create the MCP server

Follow the patterns in [MCP Server Patterns](architecture.md#mcp-server-patterns). Use `plugins/pddl-solver/server/solver_server.py` as a reference (noting it is Tier 3).

### 5. Create the launch script

See [Launch Script Patterns](architecture.md#launch-script-patterns) for tier-specific templates.

### 6. Create enforcement rules and permissions

Copy `CLAUDE.md` and `.claude/settings.json` from an existing plugin (e.g., `plugins/pddl-solver/`) and adapt the plugin name, description, and tool names.

### 7. Create at least one skill

Create `skills/<skill-name>/SKILL.md` with YAML frontmatter:
- `name` and `description` in frontmatter (description lists activation triggers)
- Lead with mandatory rules (bold "MUST", "NEVER", "ALWAYS")
- List all MCP tools with parameters and return types
- Include error handling guidance (report verbatim, never invent fallback)

### 8. Register in marketplace catalogs

Add an entry to **both**:
- `.claude-plugin/marketplace.json`
- `.cursor-plugin/marketplace.json`

The `source` field must match the plugin directory path exactly.

### 9. Verify

```bash
bash install_marketplace.sh                    # auto-discovery check
bash plugins/<name>/tests/verify.sh            # smoke test all MCP tools
```

### 10. Update documentation

Add your plugin to the "Available Plugins" section in both `CLAUDE.md` and `README.md`.

## Verification

Each plugin must have a test/verify script that exercises all declared MCP tools.

```bash
bash plugins/<name>/tests/verify.sh
```

- If `.mcp.json` exposes N tools, the verify script must test all N
- Use inline test data — don't depend on external fixture files
- Run verification before committing server or infrastructure changes

## Testing a Branch

To validate branch changes on another machine before merging, see [Branch Testing](branch-testing.md).
