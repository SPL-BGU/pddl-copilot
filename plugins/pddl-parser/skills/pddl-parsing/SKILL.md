---
name: pddl-parsing
description: Use when the user asks to understand a PDDL domain or problem, trace a plan step-by-step, debug why an action fails, explore what actions are possible from a state, or check PDDL structure without Docker.
allowed-tools: mcp__pddl-parser__get_trajectory, mcp__pddl-parser__inspect_domain, mcp__pddl-parser__inspect_problem, mcp__pddl-parser__check_applicable, mcp__pddl-parser__diff_states, mcp__pddl-parser__normalize_pddl, mcp__pddl-parser__get_applicable_actions
---

## You CANNOT reliably compute PDDL states or action effects

LLMs fail at tracking predicate sets through action sequences. Always use the parser tools — do not manually simulate, trace, or guess state changes.

### Available tools

**Understand structure:**
- `inspect_domain(domain, problem?, parser?)` — Domain structure: actions, predicates, types. Add problem for objects, init, goal.
- `inspect_problem(domain, problem, parser?)` — Problem details: objects, initial state, goal conditions.

**Debug and trace:**
- `get_trajectory(domain, problem, plan, parser?)` — Simulate a plan step-by-step, get full state-action-state trace.
- `check_applicable(domain, problem, state, action, parser?)` — Test if an action is applicable; shows satisfied/unsatisfied preconditions.
- `diff_states(state_before, state_after)` — Compare two states: what was added, removed, unchanged.

**Explore and normalize:**
- `get_applicable_actions(domain, problem, state?, max_results?, parser?)` — List all applicable grounded actions in a state.
- `normalize_pddl(content, domain?, output_format?)` — Parse PDDL into structured JSON; quick syntax check without Docker.

### Default workflow: debug a failing plan

1. `get_trajectory(domain, problem, plan)` — find where execution fails
2. `check_applicable(domain, problem, state_at_failure, failing_action)` — identify which preconditions are unsatisfied
3. `inspect_domain(domain)` — understand the action's full definition if needed
4. Report the failure cause and suggest a fix

### Exploration workflow: understand a new domain

1. `inspect_domain(domain, problem)` — get full structure with grounded details
2. `get_applicable_actions(domain, problem, "initial")` — see what actions are possible
3. Walk the user through the domain's mechanics

### What you MUST NOT do

- Do NOT manually trace action effects or compute resulting states — use `get_trajectory` or `check_applicable`
- Do NOT guess predicates, types, or action parameters from memory — use `inspect_domain` or `inspect_problem`
- Do NOT claim a plan is valid or invalid without running it through `get_trajectory`
- Do NOT invent results if a tool fails — report the error verbatim

### Input formats

All tools accept either inline PDDL content strings or absolute file paths. State parameters accept `"initial"` or a JSON array like `["(clear a)", "(on a b)"]`.

Action strings are case-insensitive and accept several forms: `(pick-up a)`, `pick-up a`, and `pick-up(a, b)`. Inline `;` comments are stripped. Unknown action/object names return a fuzzy "did you mean" suggestion.

### Parser backends

Both backends are always available. Default (null) tries unified-planning first, then falls back to pddl-plus-parser.
- **unified-planning** (default): STRIPS + ADL features (`:conditional-effects`, `:existential-preconditions`, `:universal-preconditions`, `:disjunctive-preconditions`)
- **pddl-plus-parser**: STRIPS + numeric fluents (`:functions`, `increase`, `decrease`)

If the domain uses numeric fluents, pass `parser="pddl-plus-parser"`. For ADL or plain STRIPS, let auto-select handle it.

### Cross-plugin workflows (optional)

- **Solve then trace**: After `classic_planner` returns a plan (pddl-solver, if installed), use `get_trajectory` to trace execution.
- **Write then validate**: After writing PDDL, use `normalize_pddl` for a quick syntax check. For thorough validation, use `validate_pddl_syntax` (pddl-validator, if installed).

### If a tool returns an error

1. **"No PDDL parser backend available"** — The Python environment is broken. Tell the user to delete `.venv/` in the plugin directory and restart Claude Code.
2. **"All parsers failed"** — The PDDL is likely malformed. Ask the user to check syntax. Try `normalize_pddl` for a structured error message.
3. **"File not found"** — The path is wrong. Verify the file exists and use an absolute path.
