# Changelog

## 2.4.0

Sweep-5 tool-use error UX improvements. Motivated by ~17.6k silent failures observed when small models (Qwen3.5_0.8B, Qwen3.5_4B) called tools with missing or wrong-typed args and FastMCP's pydantic dump was unparseable; see the sweep-5 report in the experiments sibling repo for full numbers.

- **Structured arg-error payload.** A `_StructuredArgErrorFastMCP` subclass intercepts pydantic `ValidationError` and emits a fixed 7-key payload (`error/errcode/tool/missing/required/supplied/message`) as `isError=True` content, instead of FastMCP's opaque `"Error executing tool ..."` string. `errcode` is one of `missing_required_arg` or `arg_validation_failed`; the latter now names the offending argument from pydantic's `loc[0]`.
- **Planner-failure `message` carries a `log_tail` fragment.** The `_solve` INTERNAL_ERROR branch now appends a tail of the captured `log` to `message`, so the model can act on the failure mode without parsing the separate `log` field. The tail length is bounded by `min(400, PDDL_MAX_LOG_CHARS)` so the env-var lever (used by small-context callers) cannot be exceeded.
- **`_ensure_file` error wording is clearer** for inputs that are neither PDDL content nor a file path. Bare problem labels (e.g. `"BW-rand-3"`) now get an actionable message describing what valid input shapes look like.
- **`mcp` / `pydantic` are now version-pinned** in `requirements.txt` to `mcp>=1.27,<2.0` and `pydantic>=2.13,<3.0`. The wrapper above touches FastMCP's `_tool_manager` / `tool.fn_metadata.arg_model` (underscored / undocumented), so an MCP-SDK major bump could break it; the pin upper-bounds the upgrade boundary.

## 2.3.1

- **Bug fix:** `numeric_planner` now works on hosts with a JDK installed but not on PATH. ENHSP shells out to bare `java`; on macOS `/usr/bin/java` is a stub that errors unless a JDK is registered under `/Library/Java/JavaVirtualMachines/`, and Homebrew's `openjdk` formula is keg-only (never registered there). Linux had analogous gaps when JDK lives under `/usr/lib/jvm` with no `update-alternatives` link. The server now probes for a working JDK at module load and exports `JAVA_HOME` / prepends to `PATH` so ENHSP subprocesses inherit a usable environment.
- Resolution order: if `java` on PATH already works at >=17, no env mutation (ENHSP resolves it on its own). Otherwise: respect existing working `$JAVA_HOME` → `/usr/libexec/java_home -v 17+` (macOS, which covers `/Library/Java/JavaVirtualMachines/*`) → Homebrew keg-only globs `/opt/homebrew/opt/openjdk*` and `/usr/local/opt/openjdk*` (macOS) → `/usr/lib/jvm/*` (Linux). Falls through to the existing friendly "Java runtime not found" error when no JDK is installed.
- Per-probe `java -version` timeout is 2s (down from 5s); a healthy JDK responds in <100ms, so 2s is plenty of slack and bounds the worst-case startup latency on hosts with multiple JDKs in `/usr/lib/jvm`.
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
