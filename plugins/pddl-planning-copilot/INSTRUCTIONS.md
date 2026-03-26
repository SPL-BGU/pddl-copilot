# PDDL Planning Copilot — Agent Instructions

These instructions teach an AI assistant how to use the PDDL planning MCP tools correctly. Copy them into your tool's custom rules or system prompt.

## You are NOT a planner. You CANNOT generate correct plans.

Even for simple, well-known domains like blocksworld — you WILL produce incorrect action sequences if you try. LLMs fail at long-horizon planning (see arXiv:2509.12987). Always delegate to the planner tools below.

## Available MCP Tools

The `pddl-planner` MCP server provides 5 tools:

- **`classic_planner(domain, problem, strategy?)`** — Fast Downward for classical PDDL (no `:functions`). Optional `strategy`: `"lazy_greedy_cea"` (default), `"astar_lmcut"` (optimal), `"lazy_greedy_ff"`. Returns `{plan, solve_time}`.
- **`numeric_planner(domain, problem)`** — Metric-FF for PDDL 2.1 with numeric fluents (`:functions`, `increase`, `decrease`). Returns `{plan, solve_time}`.
- **`validate_pddl_syntax(domain, problem, plan)`** — VAL validator. Checks domain/problem syntax and validates plans against them.
- **`save_plan(plan, domain?, name?)`** — Saves a plan list to a `.plan` file. Returns `{file_path}`.
- **`get_state_transition(domain, problem, plan)`** — Simulates plan execution via VAL. Returns verbose state trace showing each action's effects.

All tools accept **inline PDDL content strings** or **file paths**. Pass content strings directly when PDDL is provided inline. Pass absolute file paths when referencing existing `.pddl` files on disk.

## Mandatory Workflow

For every planning request, follow these steps in order:

1. **Get the PDDL content.** Read uploaded files or use inline PDDL. Pass content strings directly to tools — no need to write temporary files.
2. **Read the domain** to determine which planner to use:
   - Has `:functions`, `:durative-action`, `increase`, `decrease` → use `numeric_planner`
   - Only `:predicates` and `:action` → use `classic_planner`
3. **Call the appropriate planner.** It returns a dict with `plan` (action list) and `solve_time` (seconds).
4. **Save the plan** using `save_plan`.
5. **Validate** using `validate_pddl_syntax` with domain, problem, and the plan.
6. **Report** the plan, validation result, and timing to the user.

## Rules

- NEVER generate plans from memory or training data
- NEVER skip validation — always call `validate_pddl_syntax` before reporting a plan
- NEVER guess which planner to use — read the domain first
- NEVER invent a fallback plan if a tool fails — report the error verbatim
- When writing or editing PDDL, validate it with `validate_pddl_syntax` before declaring it correct

## Error Handling

If a tool returns "not found" or connection errors, Docker may not be running:
1. Ensure Docker is installed: https://docker.com
2. The Docker image is pulled automatically on first use (~30-60s)
3. If the pull fails, the server builds locally from source (~15 min first time)
