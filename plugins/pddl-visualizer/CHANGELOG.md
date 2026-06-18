# Changelog

All notable changes to the pddl-visualizer plugin are documented here.

## [0.1.0] - 2026-06-18

### Added
- Initial release. Pure-pip (Tier 1) MCP server with two tools:
  - `render_state` — render a single PDDL state to a PNG/SVG using a
    domain-independent predicate-graph (objects as nodes, unary predicates as
    node property labels, binary predicates as labelled directed edges, n-ary
    predicates as square predicate-nodes, numeric fluents as node/global
    annotations, 0-arity predicates in a side panel).
  - `render_trajectory` — render a state sequence to an animated GIF or a
    filmstrip PNG, with a shared node layout across frames and optional
    highlighting of facts added at each step.
- Consumes the grounded predicate-string state/trajectory that pddl-parser and
  pddl-validator already emit (PDDL state string, JSON array, or get_trajectory
  dict) — no PDDL parsing or simulation in this plugin.
- Rendering stack: networkx (layout), matplotlib/Agg (render), Pillow (GIF).
  No Docker, no graphviz/system binaries.
