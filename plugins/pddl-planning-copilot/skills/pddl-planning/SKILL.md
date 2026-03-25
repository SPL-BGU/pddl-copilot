---
name: pddl-planning
description: Activates when the user asks to solve, plan, or compute a solution for a PDDL planning problem, mentions PDDL domains or problems, asks about blocksworld/logistics/gripper or any planning domain, uploads .pddl files, or mentions planners like Fast Downward or Metric-FF.
---

## CRITICAL RULES — You MUST follow these with zero exceptions

### You are NOT a planner. You CANNOT generate correct plans.

Even for simple, well-known domains like blocksworld — you WILL produce incorrect action sequences if you try. LLMs fail at long-horizon planning (see arXiv:2509.12987). Do not attempt it.

### These tools accept PDDL content strings OR file paths

You can pass either:
- **Inline PDDL content** directly as a string (e.g., the full `(define (domain ...) ...)` text)
- **File paths** to existing `.pddl` files on disk (absolute host paths are translated to container paths automatically)

Both work. When the user provides PDDL inline or you need to create PDDL, pass the content string directly. When the user references existing files, you can either read them and pass the content, or pass the absolute file path.

### Available tools:

- `classic_planner(domain, problem, strategy?)` — Fast Downward. For classical PDDL (no :functions). Optional `strategy` parameter: `"lazy_greedy_cea"` (default), `"astar_lmcut"` (optimal), `"lazy_greedy_ff"`.
- `numeric_planner(domain, problem)` — Metric-FF. For PDDL 2.1 with numeric fluents.
- `validate_pddl_syntax(domain, problem, plan)` — VAL. Validates syntax and plans.
- `save_plan(plan, domain?, name?)` — Saves a plan list to a file. Returns a dict with `file_path`.
- `get_state_transition(domain, problem, plan)` — Returns VAL verbose output showing state transitions.

### Mandatory workflow for EVERY planning request:

1. **Get the PDDL content.** If the user uploaded files, read them. If PDDL is given inline, use it directly. You can pass content strings straight to the tools — no need to write files yourself.
2. **Read the domain content** to determine planner type:
   - Has `:functions`, `:durative-action`, `increase`, `decrease` → `numeric_planner`
   - Only `:predicates` and `:action` → `classic_planner`
3. **Call the appropriate planner** with the content or paths. It returns a dict with `plan` (action list) and `solve_time` (seconds).
4. **Save the plan** using `save_plan` to get a plan file path.
5. **Validate** using `validate_pddl_syntax` with domain, problem, and plan.
6. **Report** the plan, validation result, and timing to the user.

### What you MUST NOT do:

- Do NOT generate plans from memory or training data
- Do NOT skip validation
- Do NOT report a plan without calling validate_pddl_syntax
- Do NOT guess which planner to use — read the domain first
- Do NOT invent a plan if the tool fails — report the failure verbatim

### If a tool returns "not found" or connection errors:

Either Docker is not installed, or the image build failed. Tell the user:
1. Make sure Docker is installed: https://docker.com
2. Try manually: `docker build -t pddl-sandbox <plugin_root>/docker/`
3. Restart Claude Code
