---
name: pddl-planning
description: Activates when the user asks to solve, plan, or compute a solution for a PDDL planning problem, mentions PDDL domains or problems, asks about blocksworld/logistics/gripper or any planning domain, uploads .pddl files, or mentions planners like Fast Downward or Metric-FF.
allowed-tools: mcp__pddl-solver__classic_planner, mcp__pddl-solver__numeric_planner, mcp__pddl-solver__save_plan
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
- `save_plan(plan, domain?, problem?, name?, output_dir?, solve_time?)` — Saves a plan list to `~/plans/` with a metadata header. Returns a dict with `file_path` (host path), `container_path`, and `plan_length`. Pass `domain` and `problem` (as paths) for informative filenames. Pass `solve_time` from the planner result to include it in the header.

### Mandatory workflow for EVERY planning request:

1. **Get the PDDL content.** If the user uploaded files, read them. If PDDL is given inline, use it directly. You can pass content strings straight to the tools — no need to write files yourself.
2. **Read the domain content** to determine planner type:
   - Has `:functions`, `:durative-action`, `increase`, `decrease` → `numeric_planner`
   - Only `:predicates` and `:action` → `classic_planner`
3. **Call the appropriate planner** with the content or paths. It returns a dict with `plan` (action list) and `solve_time` (seconds).
4. **Save the plan** using `save_plan(plan=result["plan"], domain=..., problem=..., solve_time=result["solve_time"])` to get a plan file path.
5. **Report** the plan and timing to the user. If the `pddl-validator` plugin is also installed, suggest validating the plan.

### What you MUST NOT do:

- Do NOT generate plans from memory or training data
- Do NOT guess which planner to use — read the domain first
- Do NOT invent a plan if the tool fails — report the failure verbatim

### If a tool returns "not found" or connection errors:

Either Docker is not installed, or the image build failed. Tell the user:
1. Make sure Docker is installed: https://docker.com
2. Try manually: `docker build -t pddl-sandbox <repo_root>/docker/`
3. Restart Claude Code
