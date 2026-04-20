# PDDL Validator — Plugin Rules

PDDL validation plugin using pyvalidator (pure Python, Tier 1). No Docker required.

See `skills/pddl-validation/SKILL.md` for tool reference and rules.

## Configuration

Environment variables (read once at server startup; restart the plugin to apply changes):

| Variable | Default | Effect |
|----------|---------|--------|
| `PDDL_TEMP_DIR` | `/tmp/pddl` | Scratch directory for per-request temp files. |
