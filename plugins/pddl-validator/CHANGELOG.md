# Changelog

## 2.1.1

- Bump `pddl-pyvalidator` to `>=0.1.4` to pick up the numeric-goal evaluation fix. Prior versions reported plans as `INVALID` whenever the goal contained a numeric comparison (`<=`, `>=`, `=`), affecting domains like `counters` and `farmland`. Boolean-goal domains were unaffected. No plugin API changes.

## 2.1.0

- New `verbose` parameter on `validate_pddl_syntax` (default `True`) — when `False`, the response drops the heavyweight `details` field. `report` is preserved as the primary human-readable summary.
- New `verbose` parameter on `get_state_transition` (default `True`) — when `False`, drops both `report` and `details`; the structured `steps[]` and `trajectory[]` fields already encode what the prose `report` narrates.
- Slim response shapes motivated by small-context callers (e.g., Ollama) that truncate multi-KB responses. Default (`verbose=True`) preserves the original response shape.
