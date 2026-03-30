---
name: pddl-parsing
description: Activates when the user asks to inspect, parse, or understand PDDL domains/problems, generate trajectories, check action applicability, compare states, normalize PDDL, or explore applicable actions.
allowed-tools: mcp__pddl-parser__get_trajectory, mcp__pddl-parser__inspect_domain, mcp__pddl-parser__inspect_problem, mcp__pddl-parser__check_applicable, mcp__pddl-parser__diff_states, mcp__pddl-parser__normalize_pddl, mcp__pddl-parser__get_applicable_actions
---

# PDDL Parsing & Introspection Skill

## CRITICAL RULES

1. **Always use tools** for PDDL analysis. Do NOT fabricate state representations, action effects, or applicability results — LLMs cannot reliably compute these.
2. **Report errors verbatim** from tool output. Common causes: mismatched domain/problem names, undefined actions, type mismatches.
3. **Use `inspect_domain` before answering structural questions** about a domain (actions, predicates, types). Do not guess from reading raw PDDL.
4. **Use `check_applicable` to debug plan failures.** When a plan fails at step N, check the failing action against the state at that point.

## Input Formats (all tools)

- **Inline content**: strings starting with `(`, `;`, or containing `(define ` are treated as PDDL content
- **File paths**: absolute paths to existing `.pddl` files
- **State parameters**: either the string `"initial"` or a JSON array of predicate strings like `["(clear a)", "(on a b)"]`

## Tools

### `inspect_domain(domain)` -> structured JSON

Returns the domain's name, requirements, type hierarchy, predicates with parameter signatures, and actions with parameters, preconditions, and effects.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `domain`  | Yes | PDDL domain content string or absolute file path |

**Returns:**
```json
{
  "name": "blocksworld",
  "requirements": [":strips", ":typing"],
  "types": {"block": "object"},
  "predicates": [{"name": "on", "parameters": {"?x": "block", "?y": "block"}}],
  "actions": [{"name": "pick-up", "parameters": {"?x": "block"}, "precondition": "(and ...)", "effect": "(and ...)"}]
}
```

### `inspect_problem(domain, problem)` -> structured JSON

Returns the problem's name, objects with types, initial state predicates, goal conditions, and counts.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `domain`  | Yes | PDDL domain content string or absolute file path |
| `problem` | Yes | PDDL problem content string or absolute file path |

**Returns:**
```json
{
  "name": "bw1", "domain_name": "blocksworld",
  "objects": [{"name": "a", "type": "block"}],
  "init": ["(clear a)", "(handempty )", "(ontable a)"],
  "goal": ["(on a b)"],
  "num_objects": 2, "num_init_facts": 5, "num_goal_conditions": 1
}
```

### `check_applicable(domain, problem, state, action)` -> applicability report

Checks whether a grounded action is applicable in a given state. Reports which preconditions are satisfied/unsatisfied and what effects would be applied.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `domain`  | Yes | PDDL domain content string or absolute file path |
| `problem` | Yes | PDDL problem content string or absolute file path |
| `state`   | Yes | `"initial"` or JSON array of predicate strings |
| `action`  | Yes | Grounded action call, e.g. `"(pick-up a)"` |

**Returns:**
```json
{
  "applicable": true,
  "satisfied_preconditions": ["(clear a)", "(handempty )", "(ontable a)"],
  "unsatisfied_preconditions": [],
  "would_add": ["(holding a)"],
  "would_delete": ["(clear a)", "(handempty )", "(ontable a)"]
}
```

### `get_trajectory(domain, problem, plan)` -> trajectory JSON

Parses domain and problem, simulates plan step-by-step, returns full state-action-state trajectory.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `domain`  | Yes | PDDL domain content string or absolute file path |
| `problem` | Yes | PDDL problem content string or absolute file path |
| `plan`    | Yes | Plan content (one action per line) or absolute file path |

**Returns:**
```json
{
  "trajectory": {
    "1": {"state": "(:init ...)", "action": "(pick-up a)"},
    "2": {"state": "(:state ...)", "action": "(stack a b)"}
  },
  "final_state": "(:state ...)",
  "num_steps": 2
}
```

### `diff_states(state_before, state_after)` -> state comparison

Computes the difference between two states: added, removed, and unchanged predicates.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `state_before` | Yes | JSON array of predicate strings |
| `state_after`  | Yes | JSON array of predicate strings |

**Returns:**
```json
{
  "added": ["(on a b)"],
  "removed": ["(holding a)"],
  "unchanged": ["(ontable b)"]
}
```

### `normalize_pddl(content, output_format)` -> normalized PDDL

Parses PDDL domain content and re-serializes in normalized form. Lightweight Tier-1 syntax check (no Docker/VAL).

| Parameter | Required | Description |
|-----------|----------|-------------|
| `content` | Yes | PDDL domain content string |
| `output_format` | No | `"pddl"` (default) for normalized text, `"json"` for structured inspection |

**Returns:**
```json
{"valid": true, "type": "domain", "normalized": "(define (domain ...) ...)", "warnings": []}
```

### `get_applicable_actions(domain, problem, state, max_results)` -> action list

Enumerates all applicable grounded actions in a given state.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `domain`  | Yes | PDDL domain content string or absolute file path |
| `problem` | Yes | PDDL problem content string or absolute file path |
| `state`   | No | `"initial"` (default) or JSON array of predicate strings |
| `max_results` | No | Maximum results to return (default: 50) |

**Returns:**
```json
{
  "applicable_actions": ["(pick-up a)", "(pick-up b)"],
  "count": 2,
  "truncated": false
}
```

## Error Format (all tools)

```json
{"error": true, "message": "description of what went wrong"}
```

## Cross-Plugin Workflows

### Debug a Failing Plan
1. `get_trajectory(domain, problem, plan)` -> see where execution fails
2. `check_applicable(domain, problem, state_at_failure, failing_action)` -> identify which preconditions fail
3. `inspect_domain(domain)` -> understand the action's requirements

### Write and Validate PDDL
1. Write PDDL domain
2. `normalize_pddl(content)` -> quick Tier-1 syntax check (no Docker)
3. `validate_pddl_syntax(domain, problem)` -> thorough VAL check (pddl-validator plugin, if installed)
4. `inspect_domain(domain)` -> verify structure matches intent

### Solve and Trace
1. `classic_planner(domain, problem)` -> get plan (pddl-solver plugin, if installed)
2. `get_trajectory(domain, problem, plan)` -> trace full execution
3. `diff_states(state_before, state_after)` -> understand changes at each step

### Explore State Space
1. `inspect_problem(domain, problem)` -> understand initial state and objects
2. `get_applicable_actions(domain, problem, "initial")` -> what can we do first?
3. `check_applicable(domain, problem, "initial", action)` -> preview effects of a specific action
