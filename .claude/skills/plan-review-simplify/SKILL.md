---
name: plan-review-simplify
description: Create an execution plan with built-in review for correctness and simplification. Use for multi-file changes, new plugins, refactoring, or any change spanning multiple files.
disable-model-invocation: true
argument-hint: [task description]
---

## Planning Workflow with Review and Simplification

For the task described in $ARGUMENTS:

### Phase 1: Explore
1. Read all relevant existing code using Grep and Glob
2. Identify existing patterns that can be reused — especially:
   - `plugins/pddl-planning-copilot/skills/*/SKILL.md` for skill conventions
   - `plugins/pddl-planning-copilot/docker/solvers_server_wrapper.py` for MCP server patterns
   - Other plugins under `plugins/` for architecture patterns
3. Check all plugins under `plugins/` to understand cross-plugin impact
4. **If the affected plugin uses Docker (Tier 3)**: Run `docker-verifier` agent to verify baseline state

### Phase 2: Plan
Design the implementation approach covering:
- **Objective**: One sentence describing the goal
- **Analysis**: Current state, what needs to change, existing code to reuse
- **Scope classification**: Which files are marketplace-level vs plugin-scoped?
- **Architecture tier**: Which tier does this plugin use (Tier 1: pure script, Tier 2: system deps, Tier 3: Docker)? Is Docker justified? Could a simpler tier work?
- **Plugin impact**: Which plugins are affected? Does this maintain isolation?
- **Files to modify**: Table of file | action (create/modify/delete) | description
- **Execution steps**: Numbered checklist
- **Validation strategy**: Which verify/test scripts to run?

### Phase 3: Review
Before presenting the plan, review it for simplification and correctness:

**Simplification:**
- Can any proposed new file be merged into an existing file?
- Can any proposed new script reuse existing script logic?
- Are there existing patterns in `plugins/pddl-planning-copilot/` that should be followed rather than reinvented?
- Would a senior engineer say "this is more code than necessary"?

**Plugin isolation:**
- Does the change keep plugins self-contained under `plugins/<name>/`?
- Does the change avoid cross-plugin dependencies?
- Are dev-only files in root `.claude/` and user-facing files inside `plugins/`?
- Does the change avoid modifying shared infrastructure (`.claude-plugin/`, `.github/`) unnecessarily?

**Architecture appropriateness:**
- Does the plugin use the simplest architecture tier that works? (Docker is a last resort for compiled binaries only)
- Does the MCP server follow FastMCP conventions?
- Does the launch script match the plugin's tier?
- Does the verify/test script cover all declared MCP tools?

If concerns found: revise the plan. Note what changed and why.

### Phase 4: Present for Approval
Present plan to user, noting:
- Open decisions requiring user input
- Any plugin isolation trade-offs
- Expected Docker build/test impact

Do NOT proceed until approved.

### Phase 5: Execute
Execute steps in order. After completion:
1. Run the affected plugin's verify/test script (Tier 3: `docker/verify.sh`, Tier 1-2: the plugin's test script)
2. Run `shellcheck` on any new or modified `.sh` files (if shellcheck is available)
3. Summarize changes, key decisions, validation results

## Fast Mode
If user says "fast mode", "just do it", or "skip planning" — execute immediately without the planning workflow.

## Simple Tasks (No Planning Required)
Skip planning for:
- Single-file edits under 50 lines
- Answering questions or explaining code
- Running verify scripts without modification
- Git operations
- Documentation-only changes within a single plugin
