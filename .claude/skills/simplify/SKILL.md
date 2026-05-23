---
name: simplify
description: Review current plan or code changes for unnecessary complexity, plugin isolation violations, and convention deviations. Flags over-engineering, MCP issues, and scope misplacement.
context: fork
agent: simplifier
argument-hint: [description of what to review]
paths: plugins/**
---

Review the current work for unnecessary complexity and correctness.

> **Layering with bundled `/code-review`:** As of Claude Code v2.1.147, bundled `/code-review` (formerly `/simplify`) handles general correctness at the chosen effort level (e.g. `/code-review high`). This skill adds project-specific concerns the bundled reviewer cannot know: plugin-isolation boundaries, MCP/FastMCP conventions, architecture-tier appropriateness, and scope placement (dev vs user-facing). Run both — `/code-review high` first or in parallel.


$ARGUMENTS

If no specific target is given, review the most recent changes (check git diff or the current plan).

Key reference files for convention review:
- plugins/pddl-solver/server/solver_server.py — MCP server patterns
- plugins/pddl-solver/scripts/launch-server.sh — Launch script patterns
- plugins/pddl-solver/tests/verify.py — Smoke test patterns
