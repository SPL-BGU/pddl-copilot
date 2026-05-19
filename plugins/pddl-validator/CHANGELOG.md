# Changelog

## 2.2.1

- **Bug fix (behavior change), now upstream:** `validate_pddl_syntax` no longer leaks the misleading `"Plan is VALID"` / `"Plan is INVALID"` line in the `report` field when no plan was executed (domain-only or domain+problem calls). The fix lives upstream in pyvalidator 0.1.5 (`SPL-BGU/pyvalidator#1`): the report formatter's "Goal Check" block is now gated on `"execution" in result.phases`, so the misleading verdict line is only emitted on actual plan-execution paths. Requirements pin bumped to `pddl-pyvalidator>=0.1.5`. The plugin-side `_strip_plan_verdict_lines` workaround introduced during PR #50 review is removed — never shipped on `main`.
- **Edge case preserved:** an empty plan (`plan=[]` or empty file) is still validated through the full plan-execution path — correct when the initial state already satisfies the goal, in which case `"Plan is VALID"` is legitimately retained.
- `validate_pddl_syntax.plan` and `get_state_transition.plan` now accept `list[str]` in addition to the existing `str` (content or path) form. The list is materialized as a newline-joined file internally. Existing callers passing strings are unaffected.
- Docstring rewrite for `validate_pddl_syntax` clarifies the three modes (syntax / consistency / plan execution) so the tool's broader scope matches its name.

## 2.1.1

- Bump `pddl-pyvalidator` to `>=0.1.4` to pick up the numeric-goal evaluation fix. Prior versions reported plans as `INVALID` whenever the goal contained a numeric comparison (`<=`, `>=`, `=`), affecting domains like `counters` and `farmland`. Boolean-goal domains were unaffected. No plugin API changes.

## 2.1.0

- New `verbose` parameter on `validate_pddl_syntax` (default `True`) — when `False`, the response drops the heavyweight `details` field. `report` is preserved as the primary human-readable summary.
- New `verbose` parameter on `get_state_transition` (default `True`) — when `False`, drops both `report` and `details`; the structured `steps[]` and `trajectory[]` fields already encode what the prose `report` narrates.
- Slim response shapes motivated by small-context callers (e.g., Ollama) that truncate multi-KB responses. Default (`verbose=True`) preserves the original response shape.
