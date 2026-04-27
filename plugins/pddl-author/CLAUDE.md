# PDDL Author — Plugin Rules

PDDL authoring and iterative fix-loop plugin. Pure skill (no MCP server, no Python deps). Orchestrates the sibling plugins `pddl-validator`, `pddl-parser`, and `pddl-solver` as the source of ground truth — does not import their code.

Two skills:
- `pddl-authoring` — draft a PDDL domain (and optional problem) from a natural-language description, or revise an existing draft from human feedback.
- `pddl-fixing` — given a draft domain, an intent description, and at least one anchor problem, iterate fix → parse → validate → plan → trajectory until all checks pass or escalate to human.

## Dependencies (runtime)

These skills call MCP tools from sibling plugins. They are **soft dependencies** — the skills detect missing tools and report them to the user rather than failing silently. For full functionality, install:

- `pddl-validator` (required) — `validate_pddl_syntax`, `get_state_transition`
- `pddl-parser` (required) — `normalize_pddl`, `inspect_domain`, `inspect_problem`, `get_trajectory`
- `pddl-solver` (recommended for `pddl-fixing`) — `classic_planner`, `numeric_planner`

The author plugin itself ships zero binaries and zero Python deps.

## Scope boundaries

- **In scope**: drafting PDDL from descriptions, applying human-feedback edits, running an iterative fix-loop against an anchor problem.
- **Out of scope**: experimentation, benchmarking, or automated evaluation across many domains. Those belong in a separate research project — this repo is functional implementation only.
