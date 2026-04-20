# PDDL Solver — Plugin Rules

PDDL planning plugin using Fast Downward (via up-fast-downward) and ENHSP (via up-enhsp) through unified-planning. Pure Python/pip (Tier 1), no Docker required. Numeric planning requires Java (OpenJDK 17+).

See `skills/pddl-planning/SKILL.md` for tool reference, mandatory workflow, and rules.

## Configuration

Environment variables (read once at server startup; restart the plugin to apply changes). Non-integer values for integer vars raise `ValueError` naming the offending variable.

| Variable | Default | Effect |
|----------|---------|--------|
| `PDDL_TEMP_DIR` | `/tmp/pddl` | Scratch directory for per-request temp files. |
| `PDDL_TIMEOUT` | `120` | Default planner timeout in seconds for `classic_planner` / `numeric_planner`. |
| `PDDL_MAX_LOG_CHARS` | `3000` | Maximum characters of planner stderr/stdout retained in `log` on failure responses. Lower this for small-context callers (Ollama) that cannot absorb multi-KB error logs. |
