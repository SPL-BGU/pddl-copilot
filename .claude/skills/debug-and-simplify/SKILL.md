---
name: debug-and-simplify
description: Diagnose and fix issues with MCP servers, plugin configuration, or CI/CD workflows. Use when something is broken or behaving unexpectedly.
disable-model-invocation: true
argument-hint: [description of the issue or error message]
---

## Debugging Workflow with Simplification Review

For the issue described in $ARGUMENTS:

### Phase 1: Diagnose
Systematically check each layer, stopping when the root cause is found:

**Layer 0 — Runtime basics:**
1. Does the launch script exist and have execute permission?
2. Are required dependencies installed? (pip packages, system tools, etc.)
3. Can the MCP server script import its dependencies? `python3 -c "from <module> import ..."`
4. Does the server start when run directly? Check stderr for startup errors

**Layer 1 — MCP server:**
1. Can the server respond to MCP protocol? (try a basic tool invocation)
2. Do individual tools work? Run specific tool functions
3. Are tool responses in the expected format?

**Layer 2 — Plugin configuration:**
1. Is `.mcp.json` valid JSON with correct server name?
2. Does `scripts/launch-server.sh` exist and have execute permission?
3. Does `.claude/settings.json` list all tool permissions?
4. Do skills have valid YAML frontmatter?

**Layer 3 — CI/CD:**
1. Check workflow file syntax
2. Check workflow trigger conditions
3. Review recent workflow run logs

**Layer 4 — Path resolution:**
1. Is `CLAUDE_PLUGIN_ROOT` being resolved correctly?
2. Are file paths being resolved correctly relative to the plugin root?

### Phase 2: Fix
Apply the **minimal change** that resolves the root cause:
- Prefer fixing configuration over adding code
- Prefer fixing existing code over adding new files

### Phase 3: Simplify Review
Before committing the fix, review it:
1. Is this the smallest possible change that fixes the issue?
2. Does it introduce any new dependencies or complexity?
3. Could the root cause recur? If so, should we add a check to verify.sh?
4. Does the fix maintain plugin isolation?

### Phase 4: Verify
1. Run the plugin's `tests/verify.sh` to confirm the fix
2. If the issue was in CI/CD, trigger a manual workflow run: `gh workflow run <workflow>`
3. Report: what broke, why, what was fixed, verification result

### Common Issues Reference

| Symptom | Likely cause | Quick check |
|---------|-------------|-------------|
| "ModuleNotFoundError" | Missing pip/npm dependency | Check deps are installed in launch script |
| MCP server won't start | Import error or missing binary | Run server script directly, check stderr |
| Skill not appearing | Missing/invalid YAML frontmatter | Check `---` delimiters in SKILL.md |
| Tool returns empty/error | Server script bug or missing tool binary | Test tool function in isolation |
| "ModuleNotFoundError" after venv exists | Stale venv missing new deps | Delete `.venv` and rerun launch script |
