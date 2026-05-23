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

### Tool docstrings are part of the LLM-facing contract

Tool docstrings are read by LLM consumers, not just humans — vague descriptions cause real tool-selection failures (the `pddl-validator 3.0.0` split was driven by exactly this). Patterns that have paid off in this repo:

- **When-to-use framing** that contrasts the tool with its nearest neighbor (e.g., classic_planner vs numeric_planner, validate_plan vs get_state_transition).
- **Explicit return shapes** for each non-trivial branch (success / unsolvable / verbose=False), and an explicit `status` enum where applicable.
- **Named failure modes** (e.g., "PDDL parse error", "missing Java runtime") rather than a generic "error".
- **Cross-references** between near-synonymous tools so the LLM can disambiguate.

References: Anthropic [Define tools](https://platform.claude.com/docs/en/docs/agents-and-tools/tool-use/define-tools), Anthropic engineering [Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents). Canonical in-repo examples: `plugins/pddl-validator/server/validator_server.py` (validate_domain / validate_problem / validate_plan), `plugins/pddl-solver/server/solver_server.py` (classic_planner / numeric_planner).

### Skill conventions

Every SKILL.md must have YAML frontmatter (`name`, `description`), lead with mandatory rules, document all tools, and include error handling guidance. See [docs/architecture.md](../../docs/architecture.md#skill-conventions) for details.

### Verification requirements
1. **Every plugin must have `tests/verify.py`**: Smoke tests for all MCP tools. Starts the server natively and exercises each tool.
2. **Test every declared tool**: If `.mcp.json` exposes 5 tools, the verify script must test all 5.
3. **Inline test data**: Do not depend on external fixture files. Define test data in the verify script.
4. **Run verification before committing server changes**: This is the equivalent of "tests must pass".
5. **CI enforces all tests**: PRs to `main` are gated by integration tests. See [docs/contributing.md](../../docs/contributing.md#verification).

### Launch script patterns

See [docs/architecture.md](../../docs/architecture.md#launch-script-patterns) for launch templates.

Launch scripts use venv creation (`uv` or `python3 -m venv`) and direct exec. See `plugins/pddl-solver/scripts/launch-server.sh` for the reference implementation.
