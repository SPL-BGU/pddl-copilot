# Changelog

## 1.3.1

- Env-overridable limits: `PDDL_MAX_GROUNDING_ATTEMPTS` (default 10000) and `PDDL_MAX_APPLICABLE_ACTIONS` (default 50, used as the fallback for `get_applicable_actions.max_results`). Motivated by small-context callers (e.g., Ollama) that truncate large tool responses.
- Non-integer values for integer env vars now raise `ValueError` naming the offending variable at server startup, instead of an opaque parse error.

## 1.3.0

- Flexible action input: tools accept `(pick-up a)`, `pick-up a`, or `pick-up(a, b)`; case-insensitive; `;` comments stripped.
- Unknown action/object errors now include fuzzy "did you mean" suggestions.
- Default backend order: try unified-planning first, fall back to pddl-plus-parser.
- Workaround for pddl-plus-parser bug: bare atomic preconditions `(holding ?x)` are wrapped in `(and ...)` before parsing.
