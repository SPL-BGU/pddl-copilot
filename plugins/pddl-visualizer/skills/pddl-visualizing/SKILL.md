---
name: pddl-visualizing
description: Use when the user asks to visualize, animate, draw, render, or "see" a PDDL plan or trajectory — to turn a domain + problem + plan into a standalone animated HTML file that shows each step. NOT for computing a plan (use pddl-solver) or proving validity (use pddl-validator).
allowed-tools: Write, mcp__pddl-parser__get_trajectory, mcp__pddl-parser__inspect_domain, mcp__pddl-parser__inspect_problem, mcp__pddl-solver__classic_planner, mcp__pddl-solver__numeric_planner
---

## CRITICAL RULES — zero exceptions

### You MUST NOT hand-simulate states — get them from the parser

LLMs cannot reliably track predicate sets through an action sequence. The state at each step MUST come from `get_trajectory(domain, problem, plan)` (pddl-parser). Never guess, simulate, or "fill in" a state yourself. Every frame in the output is built from a state the parser returned — nothing else.

If `pddl-parser` is not installed, **stop** and tell the user. Do not produce a visualization from invented state.

### The output is ONE self-contained file that opens offline

The deliverable is a single `.html` file with **all** CSS and JS inline. No server, no build step, no CDN, no `<script src=...>`, no network access. It must render by double-clicking the file in any browser. No React/Vue/D3/external frameworks — plain inline JS + SVG only.

### You visualize the trajectory; you do not judge it

Render exactly what the trajectory reports. Do not claim the plan is "valid", "optimal", or "correct" — that is `pddl-validator`'s job. `get_trajectory` **assumes the plan is valid** and returns no per-step verdict; if it errors, treat the plan as invalid — stop, say so, and suggest the user validate it with `pddl-validator` (`validate_plan` / `get_state_transition`) first. Never invent frames to paper over an error.

## Workflow

1. **Obtain the plan.**
   - If the user supplied a plan, use it verbatim.
   - If they have only a domain + problem and want a plan first: if `pddl-solver` is available, call `classic_planner` (or `numeric_planner` for numeric/PDDL 2.1 domains) and use the returned plan. If the solver is not installed, ask the user to provide a plan or install `pddl-solver`.

2. **Get the ground-truth trajectory.** Call `get_trajectory(domain, problem, plan)`. This returns the state before/after each action — the single source of truth for every frame. It assumes the plan is valid; if it returns an error, do not guess — report that the plan appears invalid and suggest validating it with `pddl-validator` first.

3. **Read structure for layout.** Call `inspect_problem` (objects, init) and `inspect_domain` (predicates with arities, types) so you know the node set and which predicates are unary/binary.

4. **Propose a one-screen scene mapping** (the visual contract) — a compact table the user can audit:
   - Which objects become **nodes**.
   - Which **binary** predicates become labeled **edges** (e.g. `(connected ?a ?b)`, `(road-between ?a ?b)`).
   - Which **unary** predicates become node **badges/state** (e.g. `(holding ?x)`, `(clear ?x)`).
   - Which predicate positions a movable object (e.g. `(at ?obj ?loc)` places `?obj` on the `?loc` node).

   Default to **Generic mode** (below). Show the mapping and proceed unless the user redirects you — one turn, not an interview.

5. **Generate the HTML** per the output spec below, embedding the trajectory frames, and **Write** it to disk. Default path: alongside the problem file as `<problem-stem>-plan.html`, or wherever the user asks.

6. **Report**: the file path, a one-line "open this in your browser" instruction, the mapping used, and the number of steps.

## Tools you may call

All accept inline PDDL content **or** an absolute file path.

- `get_trajectory(domain, problem, plan, parser?)` (pddl-parser) — the state before/after each action; the source of every frame. `plan` may be a list of action strings, a newline-separated string, or a path. **Assumes the plan is valid** — no per-step verdict, so if it errors, treat the plan as invalid (see step 2).
- `inspect_domain(domain, problem?, parser?)` (pddl-parser) — predicates (with arities), types, actions. Use to tell unary predicates (badges) from binary ones (edges).
- `inspect_problem(domain, problem, parser?)` (pddl-parser) — objects and initial state; your node set.
- `classic_planner(domain, problem, strategy?)` (pddl-solver) — compute a plan when the user has none and the domain has no `:functions`.
- `numeric_planner(domain, problem, ...)` (pddl-solver) — same, for numeric/PDDL 2.1 domains (those declaring `:functions`).

## Two render modes

**Generic mode (default — always works).** Mechanical and domain-agnostic, so it renders *something* correct for any domain:
- Objects are SVG nodes (circle/grid/force-free layout).
- Binary predicates that currently hold are labeled edges between their two object nodes.
- Unary predicates that hold are badges on the node.
- A side panel lists every true fact for the current step, with facts **added** by the last action highlighted and facts **removed** shown struck through (computed from the previous frame's state).

**Themed mode (optional — only when asked or obviously applicable).** Bespoke SVG for a familiar domain (e.g. blocks stacked into towers for blocksworld; trucks/packages drawn at location nodes for logistics; a robot gripper for gripper). Keep the same per-step fact panel as a fallback so no information is lost if the bespoke layout misses a predicate.

## Output spec — the generated HTML MUST contain

1. **Embedded data**: a JS array of frames built from `get_trajectory`. One frame per step, e.g.
   `{ step, action, facts: [...], added: [...], removed: [...] }` — `facts` are that step's true facts; `added`/`removed` are the diff vs. the previous frame.
2. **Controls**: `◀ Prev`, `▶ Play / Pause` (autoplay ~1 step/sec), `Next ▶`, a step counter (`step i / N`), and the current **action label**.
3. **A render area** (SVG) drawn from the current frame's facts per the chosen mode.
4. **A fact panel** showing the current state with added/removed highlighting.
5. **Honest length**: include exactly the frames `get_trajectory` returned — never pad or truncate. (An invalid plan is caught in step 2, before any HTML is generated.)

Keep it small and readable — one `<style>` block, one `<script>` block, no minification.

## If a sibling plugin's tool is missing

- **`pddl-parser` (`get_trajectory`) missing** → stop:
  > "I can't get the true state at each step without `pddl-parser` (`get_trajectory`), and I won't guess states. Install `pddl-parser` and re-run."
- **`pddl-solver` missing and no plan supplied** → ask the user to provide a plan or install `pddl-solver`. Do not invent a plan.

## Worked example (Generic mode, compressed)

User: *"Visualize this plan for my logistics domain."* (supplies domain, problem, and a plan: `drive t1 A B`, `load p1 t1 B`, `drive t1 B C`, `unload p1 t1 C`).

1. `get_trajectory(domain, problem, plan)` → 4 actions, 5 states; trajectory completes.
2. `inspect_problem` → objects `t1, p1, A, B, C`; `inspect_domain` → predicates `(at ?x ?l)` [binary, positions], `(in ?p ?t)` [binary, badge], `(road-between ?l1 ?l2)` [binary, edge].
3. Mapping shown:

   | predicate | role |
   |---|---|
   | `road-between` | static edge between location nodes |
   | `at` | place object on its location node |
   | `in` | badge "in t1" on the package |

4. Generate `logistics-plan.html` with 5 frames; each frame highlights the diff (e.g. step 2 adds `(in p1 t1)`, removes `(at p1 B)`).
5. Report: `logistics-plan.html` written — open it in a browser; 4 steps; trajectory completed.

## What you MUST NOT do

- Do NOT hand-simulate, guess, or "correct" states — every frame comes from `get_trajectory`.
- Do NOT claim the plan is valid/optimal/correct — that is `pddl-validator`'s job.
- Do NOT emit anything that needs a server, build, CDN, or network — one offline file only.
- Do NOT pad, truncate, or fabricate frames — emit exactly what `get_trajectory` returned.
- Do NOT pull in external JS frameworks — plain inline JS + SVG.
