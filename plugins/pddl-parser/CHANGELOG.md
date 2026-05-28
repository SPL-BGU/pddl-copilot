# Changelog

## 1.6.1

- **Fix:** the `unified-planning` backend now emits the `get_trajectory` `action` field in canonical s-expression form with the domain-resolved (lowercased) name *and* argument names — e.g. `(pick-up a)` — instead of echoing the raw input string. Previously UP returned the input verbatim (`pick-up(a)`, or `(pick-up A)` for mixed-case args), which diverged from the `pddl-plus-parser` backend and broke the documented "both backends produce identical canonical output" contract under auto-fallback. Since UP is the default backend for non-numeric domains, this affected the default trajectory output.

## 1.6.0

- `get_trajectory` docstring adds a cross-reference distinguishing it from the validator's `get_state_transition`: this tool is for clean trajectory *extraction* on known-valid plans (dual-backend, leaner shape, no diagnostics); `get_state_transition` is for *debugging* with rich per-step precondition failures. Motivated by LLM tool-selection ambiguity between the two near-synonymous names.
- SKILL.md "Write then validate" workflow updated to reference the validator's split tools (`validate_domain` / `validate_problem` / `validate_plan`) instead of the removed `validate_pddl_syntax`. Companion to pddl-validator 3.0.0.
- No behavior changes — descriptions only.

**Sources informing the description rewrite:**
- Anthropic engineering, "Writing tools for agents" — the cross-reference recommendation between near-synonymous tools is what motivated the `get_trajectory` ↔ `get_state_transition` xref: https://www.anthropic.com/engineering/writing-tools-for-agents

## 1.5.0

- `parser` parameter on all tools is now typed `Literal["pddl-plus-parser", "unified-planning"]` (was free-form `str`). Misspellings now fail at schema validation rather than reaching the runtime fallback's "Parser X not available" check. Valid values are unchanged.
- `normalize_pddl` now accepts file paths in the `content` parameter (was content-only) — paths are read and dispatched to the same code path as inline content. Brings it in line with every other tool in the suite.
- `normalize_pddl` response now includes a dedicated `errors: list[str]` field separate from `warnings`. Hard parse failures populate `errors`; `warnings` is preserved alongside (still populated with the same message) for backward compatibility — drop `warnings` reliance in new callers.
- `inspect_domain.types` and `normalize_pddl.normalized.types` no longer include the implicit `"object": null` root. Both backends (`pddl-plus-parser`, `unified-planning`) drop it for consistency.
- `get_applicable_actions` results are now sorted lexicographically before truncation. Truncated subsets are deterministic across backends and runs (previously, `max_results=50` returned an undocumented order that differed between the two backends).
- `:requirements` in `inspect_domain` / `normalize_pddl` output now preserve the order declared in the PDDL source (was alphabetized). Reconstructing PDDL from the structured output now round-trips the requirement order.
- `get_trajectory.plan` now accepts `list[str]` in addition to string/path. An empty list maps to the empty plan.
- `check_applicable` / `get_applicable_actions` docstrings now state the closed-world semantic explicitly (predicates not listed in `state` are treated as false). `check_applicable` docstring also clarifies that `would_add` / `would_delete` are returned for diagnosis even when `applicable=false` and are NOT applied.

## 1.4.0

- Env-overridable limits: `PDDL_MAX_GROUNDING_ATTEMPTS` (default 10000) and `PDDL_MAX_APPLICABLE_ACTIONS` (default 50, used as the fallback for `get_applicable_actions.max_results`). Motivated by small-context callers (e.g., Ollama) that truncate large tool responses.
- Non-integer values for integer env vars now raise `ValueError` naming the offending variable at server startup, instead of an opaque parse error.

## 1.3.0

- Flexible action input: tools accept `(pick-up a)`, `pick-up a`, or `pick-up(a, b)`; case-insensitive; `;` comments stripped.
- Unknown action/object errors now include fuzzy "did you mean" suggestions.
- Default backend order: try unified-planning first, fall back to pddl-plus-parser.
- Workaround for pddl-plus-parser bug: bare atomic preconditions `(holding ?x)` are wrapped in `(and ...)` before parsing.
