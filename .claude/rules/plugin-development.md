---
description: Plugin development guidelines — architecture tiers, MCP servers, skills, and verification
paths:
  - "plugins/**"
---

## Plugin Development Guidelines

### Architecture tiers — simplest first

Choose the simplest tier that works. All current plugins are Tier 1.

- **Tier 1 — Pure script** (preferred): pip/npm-installable deps only. Uses venv for isolation.
- **Tier 2 — System dependencies**: wraps brew/apt/cargo-installable tools.

Full tier details, examples, and launch script templates: [docs/architecture.md](../../docs/architecture.md#architecture-tiers)

### MCP server patterns (all tiers)

All MCP servers must use FastMCP, content-or-path inputs, stateless tools, error dicts, and timeout handling. See [docs/architecture.md](../../docs/architecture.md#mcp-server-patterns) for full patterns.

### Skill conventions

Every SKILL.md must have YAML frontmatter (`name`, `description`), lead with mandatory rules, document all tools, and include error handling guidance. See [docs/architecture.md](../../docs/architecture.md#skill-conventions) for details.

### Verification requirements
1. **Every plugin must have `tests/verify.sh`**: Smoke tests for all MCP tools. Starts the server natively and exercises each tool.
2. **Test every declared tool**: If `.mcp.json` exposes 5 tools, the verify script must test all 5.
3. **Inline test data**: Do not depend on external fixture files. Define test data in the verify script.
4. **Run verification before committing server changes**: This is the equivalent of "tests must pass".
5. **CI enforces all tests**: PRs to `main` are gated by integration tests. See [docs/contributing.md](../../docs/contributing.md#verification).

### Launch script patterns

See [docs/architecture.md](../../docs/architecture.md#launch-script-patterns) for launch templates.

Launch scripts use venv creation (`uv` or `python3 -m venv`) and direct exec. See `plugins/pddl-solver/scripts/launch-server.sh` for the reference implementation.
