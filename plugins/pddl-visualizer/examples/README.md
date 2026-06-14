# Example — logistics plan visualization

A worked end-to-end output of the `pddl-visualizing` skill, rendered in **themed mode** (bespoke logistics SVG — trucks and packages drawn at location nodes). Generic mode is the skill's domain-agnostic default; it keeps the same per-step fact panel but draws plain nodes/edges/badges for any domain.

- **`domain.pddl` / `problem.pddl` / `plan.solution`** — a tiny logistics instance: a truck `t1` carries package `p1` from `B` to `C` over roads `A–B–C`.
- **`logistics-plan.html`** — the generated visualization. Open it in any browser (double-click); no server, build step, or network needed.

## How it was produced

1. The plan's per-step states came from `pddl-parser`'s `get_trajectory(domain, problem, plan)` — the skill never hand-simulates state. (`parser_used: unified-planning`, 4 steps.)
2. Each returned state became one frame `{ action, facts, added, removed }`, with `added`/`removed` diffed against the previous frame.
3. The scene mapping: `location → node`, `(road ?a ?b) → edge`, `(at ?o ?l) → place ?o on node ?l`, `(in ?p ?t) → package rides on the truck`.

## Regenerate

```bash
# from repo root, with pddl-parser installed
python3 -c "
import sys; sys.path.insert(0, 'plugins/pddl-parser/server')
import parser_server as ps, json
fn = getattr(ps.get_trajectory, 'fn', ps.get_trajectory)
print(json.dumps(fn('plugins/pddl-visualizer/examples/domain.pddl',
                     'plugins/pddl-visualizer/examples/problem.pddl',
                     'plugins/pddl-visualizer/examples/plan.solution',
                     parser='unified-planning'), indent=2))
"
```

## Why this example is classic, not numeric

The renderer's frame model is **boolean-only** — `{ action, facts, added, removed }`. It draws predicate state (nodes, edges, badges, fact diff) and has no field for numeric fluent *values*. `numeric_planner` is wired into the skill only to *obtain* a plan for numeric/PDDL 2.1 domains, and `get_trajectory` can trace them — but a numeric domain would render its relational structure while silently dropping its numbers (fuel, cost, etc.). This example is plain STRIPS so that what you see is exactly what the renderer models.
