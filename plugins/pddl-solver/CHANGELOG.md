# Changelog

## 2.2.0

- **Bug fix (behavior change):** `classic_planner` / `numeric_planner` now correctly surface environment / planner-engine failures as `{"error": True, "message": ...}`. Previously, `PlanGenerationResultStatus.INTERNAL_ERROR`, `UNSUPPORTED_PROBLEM`, and `INTERMEDIATE` were lumped into a "no plan found" response with the misleading note `"Planner ran but did not find a plan."` — callers checking `if not result["plan"]` mis-diagnosed Java-missing/missing-engine errors as unsolvable problems. ENHSP without Java now returns a clear `"Java runtime not found"` message. Statuses still routed as no-plan-found: only `UNSOLVABLE_PROVEN` / `UNSOLVABLE_INCOMPLETELY` (which legitimately mean "planner concluded no plan exists").
- `save_plan.plan` is now typed `list[str]` (was bare `list` with untyped items). Schema-level only — no runtime change.
- `save_plan` docstring corrected to match actual filename behavior: `name` becomes the `<tag>` inside the `plan_<tag>.solution` pattern (not a true override); collisions are suffixed with `_N`. Defaults to `~/plans/`, auto-created. See `docs/breaking-changes.md` for the audit context that motivated this clarification.

## 2.1.0

- Pin the solver's CWD to its per-request temp dir during planner invocation. Fast Downward and ENHSP write intermediate files (`output.sas`, etc.) to CWD; previously this crashed in sandboxed environments with a read-only CWD (e.g., Antigravity) and silently polluted CWD elsewhere.
- New env var `PDDL_MAX_LOG_CHARS` (default 3000) — cap on planner stderr/stdout retained in the `log` field of failure responses. Motivated by small-context callers (e.g., Ollama) that cannot absorb multi-KB error logs.
- Non-integer values for `PDDL_TIMEOUT` or `PDDL_MAX_LOG_CHARS` now raise `ValueError` naming the offending variable at server startup, instead of an opaque parse error.
