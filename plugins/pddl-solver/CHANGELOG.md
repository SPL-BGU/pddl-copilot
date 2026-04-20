# Changelog

## 2.1.0

- Pin the solver's CWD to its per-request temp dir during planner invocation. Fast Downward and ENHSP write intermediate files (`output.sas`, etc.) to CWD; previously this crashed in sandboxed environments with a read-only CWD (e.g., Antigravity) and silently polluted CWD elsewhere.
- New env var `PDDL_MAX_LOG_CHARS` (default 3000) — cap on planner stderr/stdout retained in the `log` field of failure responses. Motivated by small-context callers (e.g., Ollama) that cannot absorb multi-KB error logs.
- Non-integer values for `PDDL_TIMEOUT` or `PDDL_MAX_LOG_CHARS` now raise `ValueError` naming the offending variable at server startup, instead of an opaque parse error.
