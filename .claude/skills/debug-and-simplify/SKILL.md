---
name: debug-and-simplify
description: Diagnose and fix issues with Docker containers, MCP servers, plugin configuration, or CI/CD workflows. Use when something is broken or behaving unexpectedly.
disable-model-invocation: true
argument-hint: [description of the issue or error message]
---

## Debugging Workflow with Simplification Review

For the issue described in $ARGUMENTS:

### Phase 1: Diagnose
First determine the plugin's architecture tier, then systematically check each layer, stopping when the root cause is found:

**Pre-check — Identify architecture tier:**
Does this plugin use Docker? Check for `docker/Dockerfile` in the plugin directory.
- If no Dockerfile → Tier 1 or 2 (skip Docker layer, go straight to Layer 1)
- If Dockerfile exists → Tier 3 (include Docker layer)

**Layer 0 — Runtime basics (all tiers):**
1. Does the launch script exist and have execute permission?
2. Are required dependencies installed? (pip packages, system tools, etc.)
3. Can the MCP server script import its dependencies? `python3 -c "from <module> import ..."`
4. Does the server start when run directly? Check stderr for startup errors

**Layer 1 — Docker (Tier 3 only, skip for Tier 1-2):**
1. Is Docker installed? `command -v docker`
2. Is Docker daemon running? `docker info`
3. Does the image exist? `docker images | grep <image-name>`
4. Can the container start? `docker run --rm <image> echo "OK"`
5. Do solver/tool binaries exist inside the container?

**Layer 2 — MCP server:**
1. Can the server respond to MCP protocol? (try a basic tool invocation)
2. Do individual tools work? Run specific tool functions
3. Are tool responses in the expected format?

**Layer 3 — Plugin configuration:**
1. Is `.mcp.json` valid JSON with correct server name?
2. Does `scripts/launch-server.sh` exist and have execute permission?
3. Does `.claude/settings.json` list all tool permissions?
4. Do skills have valid YAML frontmatter?

**Layer 4 — CI/CD:**
1. Check workflow file syntax
2. Check GHCR image visibility (must be public)
3. Check workflow trigger conditions
4. Review recent workflow run logs: `gh run list --workflow=docker-publish.yml`

**Layer 5 — Path resolution:**
1. Is `CLAUDE_PLUGIN_ROOT` being resolved correctly?
2. Is `HOST_PWD` being set and translated properly?
3. Are file paths being translated between host and container?

### Phase 2: Fix
Apply the **minimal change** that resolves the root cause:
- Prefer fixing configuration over adding code
- Prefer fixing existing code over adding new files
- If the fix requires a Docker rebuild, note the expected build time
- If the fix requires a GHCR re-push, note the CI/CD steps needed

### Phase 3: Simplify Review
Before committing the fix, review it:
1. Is this the smallest possible change that fixes the issue?
2. Does it introduce any new dependencies or complexity?
3. Could the root cause recur? If so, should we add a check to verify.sh?
4. Does the fix maintain plugin isolation?

### Phase 4: Verify
1. Run the plugin's verify/test script to confirm the fix (Tier 3: `tests/verify.sh`, Tier 1-2: the plugin's test script)
2. If the issue was in CI/CD, trigger a manual workflow run: `gh workflow run <workflow>`
3. Report: what broke, why, what was fixed, verification result

### Common Issues Reference

| Symptom | Likely cause | Quick check |
|---------|-------------|-------------|
| "ModuleNotFoundError" | Missing pip/npm dependency | Check deps are installed in launch script |
| MCP server won't start | Import error or missing binary | Run server script directly, check stderr |
| Skill not appearing | Missing/invalid YAML frontmatter | Check `---` delimiters in SKILL.md |
| Tool returns empty/error | Server script bug or missing tool binary | Test tool function in isolation |
| **(Tier 3)** "Docker not installed" | Docker Desktop not running | `docker info` |
| **(Tier 3)** Connection timeout | Image pull in progress (~30-60s) | Wait, check stderr |
| **(Tier 3)** "file not found" in tool | HOST_PWD path translation | Check `-e HOST_PWD` in docker run |
| **(Tier 3)** GHCR pull fails | Package not public | Repo Settings > Packages > visibility |
| **(Tier 3)** verify.sh all FAILED | Stale Docker image | Rebuild: `docker build -t <image> docker/` |
