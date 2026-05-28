# Changelog

## 3.1.0

Sweep-5 tool-use error UX improvements. Motivated by ~17.6k silent failures observed when small models (Qwen3.5_0.8B, Qwen3.5_4B) called tools with missing or wrong-typed args and FastMCP's pydantic dump was unparseable; see the sweep-5 report in the experiments sibling repo for full numbers.

- **Structured arg-error payload.** A `_StructuredArgErrorFastMCP` subclass intercepts pydantic `ValidationError` and emits a fixed 7-key payload (`error/errcode/tool/missing/required/supplied/message`) as `isError=True` content, instead of FastMCP's opaque `"Error executing tool ..."` string. `errcode` is one of `missing_required_arg` or `arg_validation_failed`; the latter now names the offending argument from pydantic's `loc[0]`.
- **`validate_plan` and `get_state_transition`: structured `PRECONDITION_ERROR`.** pyvalidator raises (rather than returning a structured INVALID) when a numeric plan references a fluent the problem didn't initialize — common on farmland and zenotravel-numeric broken-plan fixtures. Both tools now catch this and return `{valid: False, status: "PRECONDITION_ERROR", report: msg}`; `verbose=True` adds the documented `details` key.
- **`PRECONDITION_ERROR` is a new status enum value.** Additive: returned only on the unknown-fluent path where previously the response was `{error: True, message: "Validation error: ..."}`. Existing `VALID/INVALID/SYNTAX_ERROR/STRUCTURE_ERROR` values unchanged.
- **`_ensure_plan_file` accepts more LLM serialization shapes.** Python-list-literal strings (`"['(pick-up a)', '(stack a b)']"`) are parsed with `ast.literal_eval` when every element is a string; multi-line plan text (with or without surrounding parens) is written verbatim and let through to pyvalidator. Bare single-token labels (e.g. `"BW-rand-3"`) still error, with a clearer message naming valid input shapes.
- **`mcp` / `pydantic` are now version-pinned** in `requirements.txt` to `mcp>=1.27,<2.0` and `pydantic>=2.13,<3.0`. The wrapper above touches FastMCP's `_tool_manager` / `tool.fn_metadata.arg_model` (underscored / undocumented), so an MCP-SDK major bump could break it; the pin upper-bounds the upgrade boundary.
- **Fix: `get_state_transition` now always includes `status`.** Previously a `STRUCTURE_ERROR`/`SYNTAX_ERROR` (undefined action, wrong arity, malformed PDDL) returned `{"valid": false, "steps": [], "trajectory": []}` — indistinguishable from a plan that executed and failed. Callers can now read `status` to tell "never simulated" apart from "ran and failed". Matches the `validate_*` family.
- **Fix: false-passing `test_malformed_pddl` regression test.** The old assertion `"error" not in result or status == "SYNTAX_ERROR"` short-circuited to pass whenever no exception-`error` key existed, and its input `(define (domain broken))` was a valid empty domain — so it never exercised rejection. Now uses genuinely malformed input (unbalanced parens) asserting rejection as `SYNTAX_ERROR`.

## 3.0.0 — BREAKING

**Tool surface change.** `validate_pddl_syntax` is split into three task-aligned tools to eliminate the argument-shape polymorphism that was the dominant cause of plan-validation failures in downstream LLM consumers (a `(domain, problem)` call returns the consistency verdict, *not* the plan verdict — the previous name "validate_pddl_syntax" did not advertise that gotcha).

**New tools:**
- `validate_domain(domain, verbose?)` — pyvalidator `validate_syntax(domain, None)`. Domain syntax + types + structural consistency.
- `validate_problem(domain, problem, verbose?)` — pyvalidator `validate_syntax(domain, problem)`. Domain/problem consistency.
- `validate_plan(domain, problem, plan, verbose?)` — pyvalidator `validate(domain, problem, plan)`. Plan correctness against the model.

**Removed:**
- `validate_pddl_syntax` — no shim. Replace per arg shape:
  | Old call | New call |
  |---|---|
  | `validate_pddl_syntax(domain)` | `validate_domain(domain)` |
  | `validate_pddl_syntax(domain, problem)` | `validate_problem(domain, problem)` |
  | `validate_pddl_syntax(domain, problem, plan)` | `validate_plan(domain, problem, plan)` |

`get_state_transition` is unchanged behaviorally; docstring rewritten to make the `verbose=False` asymmetry with `validate_plan` explicit (this tool drops BOTH `report` and `details`; `validate_*` drops `details` only).

All three new validators preserve the `verbose=True/False` shape from 2.2.1 — verbose=False drops `details` only, keeps `report`.

**Sources informing the description rewrite:**
- Anthropic, "Define tools" (3–4 sentence rule, parameter/return-shape format, examples): https://platform.claude.com/docs/en/docs/agents-and-tools/tool-use/define-tools
- Anthropic engineering, "Writing tools for agents" (cross-references between near-synonymous tools; when-to-use framing): https://www.anthropic.com/engineering/writing-tools-for-agents
- Berkeley Function-Calling Leaderboard methodology (BFCL): https://gorilla.cs.berkeley.edu/blogs/8_berkeley_function_calling_leaderboard.html
- Grader anchor `pddl-copilot-experiments/pddl_eval/scoring.py:65-88` (`_call_matches_validate_task`) — defines the task↔arg-shape mapping that the previous polymorphic `validate_pddl_syntax` failed to advertise. The split tools eliminate this gate by making task→tool 1:1.

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
