# PDDL Parser — Plugin Rules

PDDL parsing and trajectory generation plugin with dual-backend support (pddl-plus-parser and unified-planning) via MCP. Pure Python (Tier 1), no Docker required. Both backends produce identical canonical output.

See `skills/pddl-parsing/SKILL.md` for usage rules and workflows.

## Configuration

Environment variables (read once at server startup; restart the plugin to apply changes). Non-integer values for integer vars raise `ValueError` naming the offending variable.

| Variable | Default | Effect |
|----------|---------|--------|
| `PDDL_MAX_GROUNDING_ATTEMPTS` | `10000` | Cap on grounding attempts in backend search when enumerating action instances. Raise for large numeric domains. |
| `PDDL_MAX_APPLICABLE_ACTIONS` | `50` | Default for `get_applicable_actions.max_results` when the caller does not pass one. Lower this for small-context callers (Ollama) to prevent response truncation. |
