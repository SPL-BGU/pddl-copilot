---
name: pddl-visualization
description: Activates when the user asks to visualize, draw, render, picture, diagram, or "show" a PDDL state, the initial/goal state, or a plan/trajectory/trace as an image, GIF, or animation. Also when the user wants to see what a state looks like or watch a plan execute step by step.
allowed-tools: mcp__pddl-visualizer__render_state, mcp__pddl-visualizer__render_trajectory
---

## CRITICAL RULES — You MUST follow these with zero exceptions

### This plugin renders states, it does NOT parse PDDL or simulate plans

`render_state` / `render_trajectory` take an already-grounded state (a list of
predicates), not a domain/problem/plan. They never run a planner or a parser.

- To draw a **single state**, you must already have the predicate list. Get it
  from a sibling plugin: `pddl-parser`'s `inspect_problem` (`init` / `goal`
  fields), `get_trajectory` (per-step `state`), or `pddl-validator`'s
  `get_state_transition`.
- To draw a **trajectory**, get it from `pddl-parser`'s `get_trajectory` and
  pass the whole result dict straight through.
- NEVER hand-write or guess a state. If you don't have a grounded state, obtain
  it from the parser/validator first.

### Always show the result

Both tools write an image file and return its `image_path`. After calling a
tool, **Read that path** so the image is displayed to the user. Report the path.

### Report errors verbatim

If a tool returns `{"error": True, "message": ...}`, report the message. Do not
invent a fallback or fabricate an image.

## How a state is drawn (domain-independent)

No per-domain configuration. The mapping is:

| Predicate | Example | Rendered as |
|-----------|---------|-------------|
| 0-arity | `(handempty)` | flag in a side panel |
| unary | `(clear a)` | property label on node `a` |
| binary | `(on a b)` | directed edge `a → b` labelled `on` |
| n-arity (≥3) | `(connected x y z)` | square predicate-node wired to each arg |
| numeric | `(= (fuel t) 5)` | `fuel=5` annotation on node `t` (or side panel if no object arg) |

## Available tools

- `render_state(state, output_path?, layout?, fmt?, title?)`
  - `state`: a PDDL state string (`(:init (on a b) (clear a) (handempty))`,
    `(:state ...)`, `(:goal ...)`, or a bare `(on a b) (clear a)` sequence), OR
    a JSON array of predicate strings `["(on a b)", "(clear a)"]`.
  - `layout`: `spring` (default), `circular`, `shell`, `kamada_kawai`.
  - `fmt`: `png` (default) or `svg`.
  - Returns `{"image_path", "format", "num_objects", "num_predicates"}`.

- `render_trajectory(trajectory, output_path?, fmt?, layout?, highlight_changes?, frame_seconds?)`
  - `trajectory`: the dict `pddl-parser`'s `get_trajectory` returns (pass it
    through directly), its inner step-mapping, or a plain list of state strings.
  - `fmt`: `gif` (default, animated) or `filmstrip` (single PNG grid of panels).
  - `highlight_changes`: default `True` — facts added at each step are drawn in
    green; each frame is titled with the action that produced it.
  - `frame_seconds`: GIF seconds per frame (default `1.2`).
  - Returns `{"image_path", "format", "num_frames"}`.

Output defaults to `~/pddl-renders/` (override with `output_path` or the
`PDDL_RENDER_DIR` env var).

## Typical workflows

**Visualize the initial state of a problem**
1. `pddl-parser inspect_problem(domain, problem)` → take the `init` list.
2. `render_state(state=<init list>, title="initial state")`.
3. Read the returned `image_path`.

**Animate a plan**
1. Get a plan (`pddl-solver`) or use one the user provided.
2. `pddl-parser get_trajectory(domain, problem, plan)` → the trajectory dict.
3. `render_trajectory(trajectory=<that dict>)` → GIF.
4. Read the returned `image_path`.
