# PDDL Visualizer — Plugin Rules

PDDL state and trajectory visualization plugin. Renders a grounded state as a
domain-independent predicate-graph (objects as nodes, unary predicates as node
properties, binary predicates as labelled edges, n-ary predicates as
predicate-nodes, numeric fluents as annotations) to PNG/SVG, and a trajectory
to an animated GIF or filmstrip PNG. Pure Python/pip (Tier 1), no Docker, no
system binaries (uses networkx + matplotlib, deliberately not graphviz/dot).

This plugin does NOT parse a domain/problem or simulate a plan. It consumes the
grounded predicate-string state that `pddl-parser` / `pddl-validator` already
emit. Obtain the state (or trajectory) from a sibling plugin first, then pass it
in. After rendering, Read the returned `image_path` to view it.

See `skills/pddl-visualization/SKILL.md` for the tool reference and workflow.

## Configuration

Environment variables (read once at server startup; restart the plugin to apply
changes).

| Variable | Default | Effect |
|----------|---------|--------|
| `PDDL_RENDER_DIR` | `~/pddl-renders` | Default directory for output images when no `output_path` is given. |
