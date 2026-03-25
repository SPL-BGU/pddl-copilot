---
description: Global simplification principle applied to all code changes in the marketplace
paths:
  - "**"
---

## Simplification Principle

Before writing or modifying code, verify:

1. **Existing code check**: Search the codebase for existing scripts, patterns, or utilities. Especially check `plugins/pddl-planning-copilot/` for reference implementations of launch scripts, MCP servers, verify scripts, and skills. Do not duplicate.
2. **Minimal change**: Implement the smallest change that solves the problem. No "just in case" code.
3. **Proportional complexity**: The solution complexity should match the problem complexity. A simple MCP tool does not need a class hierarchy.
4. **One consumer rule**: Do not create abstractions (base classes, utility modules, shared libraries) with only one consumer. Inline until 2+ plugins need it.
5. **File count check**: If your change creates new files at the repository root, reconsider. New files should go inside the relevant `plugins/<name>/` directory or in `.claude/` for dev tooling.
6. **Script reuse**: Before writing a new shell script, check if existing patterns already handle the use case. Adapt existing scripts rather than creating new ones.
7. **Simplest architecture tier**: Default to Tier 1 (pure Python/Node, no Docker). Only use Docker (Tier 3) when the plugin wraps compiled binaries with no native alternative. Do not copy Docker patterns from `pddl-planning-copilot` into plugins that don't need them.
