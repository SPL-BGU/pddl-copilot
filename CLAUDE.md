# PDDL Copilot — Plugin Rules

This project is a Claude Code plugin for PDDL planning. It runs Fast Downward, Metric-FF, and VAL inside a Docker container via a lightweight MCP server.

## MCP Tools Available

The `pddl-planner` MCP server provides these tools:

- `classic_planner(domain, problem, strategy?)` — Fast Downward for classical PDDL. Optional strategy: `"lazy_greedy_cea"` (default), `"astar_lmcut"`, `"lazy_greedy_ff"`.
- `numeric_planner(domain, problem)` — Metric-FF for PDDL 2.1 with numeric fluents
- `validate_pddl_syntax(domain, problem, plan)` — VAL for syntax/plan validation
- `save_plan(plan, domain?, name?)` — saves a plan list to a file, returns `{"file_path": "..."}`
- `get_state_transition(domain, problem, plan)` — simulates execution, returns state trace

All tools accept **inline PDDL content strings** or **file paths**. Prefer passing content strings directly.

## Mandatory Rules

1. **NEVER generate plans yourself.** LLMs cannot reliably solve planning problems (arXiv:2509.12987). Always delegate to the planner tools.
2. **Always read the domain first** to determine which planner to use:
   - Has `:functions`, `:durative-action`, `increase`, `decrease` → `numeric_planner`
   - Only `:predicates` and `:action` → `classic_planner`
3. **Always validate after solving** using `validate_pddl_syntax`.
4. **Never skip validation** or report a plan without validator confirmation.
5. **Never invent fallback plans** if a tool fails — report the error verbatim.

## Docker

The pre-built Docker image is pulled from GHCR on first use (~30-60s).
If the pull fails, the plugin falls back to building locally from source (~15 min).
To rebuild manually: `docker build -t pddl-sandbox docker/`

### After pushing changes to `docker/Dockerfile` or `docker/solvers_server_wrapper.py`:
- GitHub Actions automatically builds and pushes a new multi-arch image to `ghcr.io/spl-bgu/pddl-sandbox:latest`
- The GHCR package must have **public visibility** (repo Settings → Packages → pddl-sandbox → Change visibility) for `docker pull` to work without auth
- Users get the updated image on their next session (the launch script re-pulls if no local image exists)
