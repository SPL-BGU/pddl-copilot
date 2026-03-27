---
name: simplify
description: Review current plan or code changes for unnecessary complexity, plugin isolation violations, and convention deviations. Flags over-engineering, Docker antipatterns, MCP issues, and scope misplacement.
context: fork
agent: simplifier
argument-hint: [description of what to review]
---

Review the current work for unnecessary complexity and correctness.

$ARGUMENTS

If no specific target is given, review the most recent changes (check git diff or the current plan).

Key reference files for convention review:
- plugins/pddl-solver/server/solver_server.py — MCP server patterns
- plugins/pddl-solver/scripts/launch-server.sh — Launch script patterns
- plugins/pddl-solver/tests/verify.sh — Smoke test patterns
