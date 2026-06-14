# PDDL Visualizer — Plugin Rules

PDDL plan visualization plugin. Pure skill (no MCP server, no Python deps). Turns a domain + problem + plan into a single self-contained HTML file that animates the plan step-by-step. Orchestrates the sibling plugins `pddl-parser` (ground-truth states) and `pddl-solver` (to obtain a plan) — does not import their code.

One skill:
- `pddl-visualizing` — given a domain, a problem, and a plan (or a request to plan one first), produce a standalone animated HTML visualization of the resulting trajectory.

## Dependencies (runtime)

This skill calls MCP tools from sibling plugins. They are **soft dependencies** — the skill detects missing tools and reports them to the user rather than failing silently or inventing state. For full functionality, install:

- `pddl-parser` (required) — `get_trajectory`, `inspect_domain`, `inspect_problem`. Supplies the true state at each plan step. The skill MUST NOT hand-simulate states.
- `pddl-solver` (recommended) — `classic_planner`, `numeric_planner`. Used only when the user has no plan yet and asks to generate one before visualizing.

The visualizer plugin itself ships zero binaries and zero Python deps. Its only output is an HTML file written to disk.

## Scope boundaries

- **In scope**: rendering a known plan/trajectory as a single self-contained, animated HTML file that opens in any browser with no server, build step, or network access.
- **Out of scope**: running a live web app or server, computing plans (that is `pddl-solver`), proving plan validity (that is `pddl-validator`), and benchmarking or batch evaluation across many domains. Those belong elsewhere — this repo is functional implementation only.
