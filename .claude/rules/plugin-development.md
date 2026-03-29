---
description: Plugin development guidelines — architecture tiers, MCP servers, skills, and verification
paths:
  - "plugins/**"
---

## Plugin Development Guidelines

### Architecture tiers — simplest first

Choose the simplest tier that works. **Docker is a last resort**, not the default.

- **Tier 1 — Pure script** (preferred): pip/npm-installable deps only. No Docker.
- **Tier 2 — System dependencies**: wraps brew/apt/cargo-installable tools.
- **Tier 3 — Docker**: only when binaries must be compiled from source with no native alternative.

If the tool is `pip install`-able, `npm install`-able, or `brew install`-able — do NOT use Docker.

Full tier details, examples, and launch script templates: [docs/architecture.md](../../docs/architecture.md#architecture-tiers)

### MCP server patterns (all tiers)

All MCP servers must use FastMCP, content-or-path inputs, stateless tools, error dicts, and timeout handling. See [docs/architecture.md](../../docs/architecture.md#mcp-server-patterns) for full patterns.

### Skill conventions

Every SKILL.md must have YAML frontmatter (`name`, `description`), lead with mandatory rules, document all tools, and include error handling guidance. See [docs/architecture.md](../../docs/architecture.md#skill-conventions) for details.

### Verification requirements
1. **Every plugin must have a test/verify script**: Smoke tests for all MCP tools.
   - Tier 1-2: a test script that starts the server and exercises each tool
   - Tier 3: `tests/verify.sh` that runs tests in isolated containers
2. **Test every declared tool**: If `.mcp.json` exposes 5 tools, the verify script must test all 5.
3. **Inline test data**: Do not depend on external fixture files. Define test data in the verify script.
4. **Run verification before committing server changes**: This is the equivalent of "tests must pass".
5. **CI enforces all tests**: PRs to `main` are gated by integration tests. See [docs/contributing.md](../../docs/contributing.md#verification).

### Launch script and Docker patterns

See [docs/architecture.md](../../docs/architecture.md#launch-script-patterns) for tier-specific launch templates and Docker build/publish conventions.

Key enforcement points:
- Tier 3 launch scripts must try GHCR pull before falling back to local build
- Docker builds must use multi-stage builds and strip binaries
- GHCR packages must have public visibility
- Use `--rm` flag so containers are removed on exit
