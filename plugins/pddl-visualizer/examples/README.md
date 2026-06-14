# Example — logistics plan visualization

A worked end-to-end output of the `pddl-visualizing` skill.

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
                     'plugins/pddl-visualizer/examples/plan.solution'), indent=2))
"
```
