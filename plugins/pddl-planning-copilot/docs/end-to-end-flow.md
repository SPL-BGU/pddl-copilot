# End-to-End Flow

This document traces the full lifecycle: from pushing code, through CI, to a user's first run and tool invocation.

## Flow Diagram

```
Developer pushes to main
        │
        ▼
┌─────────────────────┐
│  CI: build & push   │  (.github/workflows/docker-publish.yml)
│  amd64 + arm64      │
│  → GHCR :latest     │
└────────┬────────────┘
         │
         ▼
User installs plugin / starts new Claude Code session
         │
         ▼
┌─────────────────────┐
│  launch-server.sh   │  (scripts/launch-server.sh)
│  docker pull GHCR   │──── fails? ──→ local build from docker/Dockerfile (~15 min)
│  docker run ...     │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  MCP server running  │  (docker/solvers_server_wrapper.py)
│  inside container    │
│  stdio transport     │
└────────┬────────────┘
         │
         ▼
Claude Code calls tools (classic_planner, numeric_planner, etc.)
         │
         ▼
Results returned → container exits → image stays cached
```

---

## 1. Push to Main (CI/CD)

**Trigger:** push to `main` that changes `docker/Dockerfile` or `docker/solvers_server_wrapper.py`, or manual `workflow_dispatch`.

**What happens:**

1. **`build-amd64`** job runs on `ubuntu-latest` (native x86_64). Compiles Fast Downward, Metric-FF, and VAL from source. Pushes the image to `ghcr.io/<owner>/pddl-sandbox:build-amd64`.

2. **`build-arm64`** job runs on `ubuntu-24.04-arm` (native ARM64). Same build, different arch. Pushes to `:build-arm64`.

3. **`merge`** job waits for both, then runs `docker buildx imagetools create` to combine the two per-arch images into a single multi-arch manifest tagged `:latest` and `:<sha>`.

The intermediate `:build-amd64` / `:build-arm64` tags are overwritten each run. Users only pull `:latest`.

See [build-push-workflow.md](build-push-workflow.md) for design decisions (why native runners, why `provenance: false`, etc.).

---

## 2. User Needs to Update

There is no explicit update command. However, updates are **not** automatic either.

`launch-server.sh` checks if the GHCR image exists locally (`docker image inspect`). If it does, it uses the cached image immediately — **it does not pull again**. This means once a user has the image, they keep that version until they manually remove it.

To get a newer image, the user must either:
- Run `docker rmi ghcr.io/spl-bgu/pddl-sandbox:latest` and restart the session (triggers a fresh pull).
- Run `docker pull ghcr.io/spl-bgu/pddl-sandbox:latest` manually.

**If the image is not cached locally** (first install or after removal):
- The script pulls from GHCR (~30-60s).
- If the pull fails (no network, GHCR down), it builds from source using `docker/Dockerfile` (~15 min).
- The local build hashes `Dockerfile + solvers_server_wrapper.py` to create a version tag. It only rebuilds when these files change.

---

## 3. Clean Start (First-Time User)

A user installs the plugin. Claude Code immediately starts the MCP server — the image pull happens at **plugin load time**, not at first tool call.

1. **Claude Code reads `.mcp.json`** — discovers the `pddl-planner` MCP server, entry point: `bash scripts/launch-server.sh`. It runs the script immediately.

2. **`launch-server.sh` runs:**
   - Checks that `docker` is installed (exits with error JSON if not).
   - Checks if `ghcr.io/spl-bgu/pddl-sandbox:latest` exists locally (it won't on first install).
   - Pulls from GHCR (~30-60s). The plugin installation appears instant because the pull output goes to stderr, not the MCP transport.
   - On pull failure: builds locally from `docker/Dockerfile` (compiles all three solvers, ~15 min).

3. **Container starts immediately after image is resolved:**
   ```
   docker run --rm -i \
     -e HOST_PWD=$PWD \
     -v $PWD:/workspace \
     -w /workspace \
     <image> python3 -m pddl_server
   ```
   - `--rm` — container is removed when session ends.
   - `-i` — stdin stays open for MCP stdio transport.
   - `-v $PWD:/workspace` — mounts the user's working directory so the server can read/write PDDL files.
   - `-e HOST_PWD` — tells the server the host-side path for path translation.

4. **MCP server is ready** — Claude Code can now call the 5 tools. Permissions are pre-approved via `.claude/settings.json`.

On subsequent sessions, the image is already cached locally. `launch-server.sh` finds it via `docker image inspect`, skips the pull entirely, and starts the container instantly.

---

## 4. Invocation (Tool Call Flow)

When the user asks Claude to solve a planning problem:

### Step 1: Skill activation

Claude Code loads `skills/pddl-planning/SKILL.md` (or `pddl-validation/SKILL.md` for authoring tasks). The skill enforces the mandatory workflow: never generate plans, always validate.

### Step 2: Domain analysis

Claude reads the domain file to determine the planner:
- Has `:functions`, `increase`, `decrease`, `:durative-action` → `numeric_planner` (Metric-FF)
- Only `:predicates` and `:action` → `classic_planner` (Fast Downward)

### Step 3: Planner call

Claude calls the appropriate tool, passing PDDL content inline or as file paths.

Inside the container:
1. `_ensure_file()` resolves the input — if it's inline content (starts with `(`), it writes it to a temp file under `/tmp/pddl/<uuid>/`. If it's a path, it translates it using `HOST_PWD`.
2. The solver runs as a subprocess with a 120-second timeout.
3. The output is parsed — Fast Downward's `sas_plan*` files or Metric-FF's stdout.
4. Temp files and solver artifacts are cleaned up.
5. Returns `{"plan": [...], "solve_time": float}` or an error dict.

### Step 4: Save plan

Claude calls `save_plan(plan)` → writes the action list to `/workspace/plan_<name>.solution`.

### Step 5: Validate

Claude calls `validate_pddl_syntax(domain, problem, plan)` → runs VAL inside the container → returns validation output. Claude only reports the plan after the validator confirms it.

### Step 6: Session ends

When the Claude Code session ends, the MCP server's stdin closes, the process exits, and `--rm` removes the container. The Docker image remains cached for the next session.
