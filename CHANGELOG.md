# Changelog

## pddl-parser 1.3.0

- Flexible action input: tools accept `(pick-up a)`, `pick-up a`, or `pick-up(a, b)`; case-insensitive; `;` comments stripped.
- Unknown action/object errors now include fuzzy "did you mean" suggestions.
- Default backend order: try unified-planning first, fall back to pddl-plus-parser.

## v2.0.0

- Docker eliminated: all plugins migrated to pure pip (see #34).
