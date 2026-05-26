# Changelog

## 2.3.1

- **Bug fix:** `numeric_planner` now works on hosts with a JDK installed but not on PATH. ENHSP shells out to bare `java`; on macOS `/usr/bin/java` is a stub that errors unless a JDK is registered under `/Library/Java/JavaVirtualMachines/`, and Homebrew's `openjdk` formula is keg-only (never registered there). Linux had analogous gaps when JDK lives under `/usr/lib/jvm` with no `update-alternatives` link. The server now probes for a working JDK at module load and exports `JAVA_HOME` / prepends to `PATH` so ENHSP subprocesses inherit a usable environment.
- Resolution order: respect existing working `$JAVA_HOME` → `/usr/libexec/java_home -v 17+` (macOS) → Homebrew keg-only globs `/opt/homebrew/opt/openjdk*` and `/usr/local/opt/openjdk*` (macOS) → `/usr/lib/jvm/*` (Linux). Falls through to the existing friendly "Java runtime not found" error when no JDK is installed.
- Error message at the Java-stub branch refined to suggest the install command and note that the plugin auto-discovers on restart (no manual `JAVA_HOME` setup required).
- `numeric_planner` docstring updated to document the auto-discovery behavior.

## 2.3.0

- Description-only upgrade for `classic_planner` and `numeric_planner` MCP tool docstrings. Motivated by LLM tool-selection failures observed in downstream consumers — the prior descriptions were terse on when-to-use, runtime requirements (Java for ENHSP only), and named failure modes.
- `classic_planner`: documents the `:functions` pivot vs `numeric_planner` accurately (durative actions unsupported by *either* planner; only the `:functions` axis selects between them); explicit "no Java required"; expanded strategy reference; named error modes including PDDL parse error.
- `numeric_planner`: documents what happens when Java is absent on macOS (clean error message) vs Linux/Windows (status-X failure with log); named error modes including PDDL parse error.
- `save_plan` left unchanged.
- No behavior changes — descriptions only.

**Sources informing the description rewrite:**
- Anthropic, "Define tools" (3–4 sentence rule, parameter/return-shape format): https://platform.claude.com/docs/en/docs/agents-and-tools/tool-use/define-tools
- Anthropic engineering, "Writing tools for agents" (when-to-use framing, named failure modes): https://www.anthropic.com/engineering/writing-tools-for-agents
- Berkeley Function-Calling Leaderboard methodology (BFCL): https://gorilla.cs.berkeley.edu/blogs/8_berkeley_function_calling_leaderboard.html

## 2.2.0

- **Bug fix (behavior change):** `classic_planner` / `numeric_planner` now correctly surface environment / planner-engine failures as `{"error": True, "message": ...}`. Previously, `PlanGenerationResultStatus.INTERNAL_ERROR`, `UNSUPPORTED_PROBLEM`, and `INTERMEDIATE` were lumped into a "no plan found" response with the misleading note `"Planner ran but did not find a plan."` — callers checking `if not result["plan"]` mis-diagnosed Java-missing/missing-engine errors as unsolvable problems. ENHSP without Java now returns a clear `"Java runtime not found"` message. Statuses still routed as no-plan-found: only `UNSOLVABLE_PROVEN` / `UNSOLVABLE_INCOMPLETELY` (which legitimately mean "planner concluded no plan exists").
- `save_plan.plan` is now typed `list[str]` (was bare `list` with untyped items). Schema-level only — no runtime change.
- `save_plan` docstring corrected to match actual filename behavior: `name` becomes the `<tag>` inside the `plan_<tag>.solution` pattern (not a true override); collisions are suffixed with `_N`. Defaults to `~/plans/`, auto-created. See `docs/breaking-changes.md` for the audit context that motivated this clarification.

## 2.1.0

- Pin the solver's CWD to its per-request temp dir during planner invocation. Fast Downward and ENHSP write intermediate files (`output.sas`, etc.) to CWD; previously this crashed in sandboxed environments with a read-only CWD (e.g., Antigravity) and silently polluted CWD elsewhere.
- New env var `PDDL_MAX_LOG_CHARS` (default 3000) — cap on planner stderr/stdout retained in the `log` field of failure responses. Motivated by small-context callers (e.g., Ollama) that cannot absorb multi-KB error logs.
- Non-integer values for `PDDL_TIMEOUT` or `PDDL_MAX_LOG_CHARS` now raise `ValueError` naming the offending variable at server startup, instead of an opaque parse error.
