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

## Parser Backends

Tools that accept a `parser` parameter can use either backend:
- **pddl-plus-parser** (default, always available): Full STRIPS/numeric support
- **unified-planning** (optional): Alternative parser with different PDDL coverage

When `parser` is null (default), the server tries pddl-plus-parser first, then falls back to unified-planning if available. Responses include a `parser_used` field indicating which backend produced the result.

## Tools

### `inspect_domain(domain, problem?, parser?)` -> structured JSON

Returns the domain's name, requirements, type hierarchy, predicates, and actions. When a problem is also provided, adds grounded details: objects, initial state, and goal — giving a complete picture of the domain-scenario.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `domain`  | Yes | PDDL domain content string or absolute file path |
| `problem` | No | PDDL problem content string or file path. Adds grounded details (objects, init, goal) |
| `parser`  | No | `"pddl-plus-parser"`, `"unified-planning"`, or null (auto-select with fallback) |

**Returns (domain only):**
```json
{
  "name": "blocksworld",
  "requirements": [":strips", ":typing"],
  "types": {"block": "object"},
  "predicates": [{"name": "on", "parameters": {"?x": "block", "?y": "block"}}],
  "actions": [{"name": "pick-up", "parameters": {"?x": "block"}, "precondition": "(and ...)", "effect": "(and ...)"}]
}
```

**Returns (domain + problem) — adds:**
```json
{
  "objects": [{"name": "a", "type": "block"}],
  "init": ["(clear a)", "(ontable a)", "(handempty)"],
  "goal": ["(on a b)"],
  "num_objects": 2, "num_init_facts": 5, "num_goal_conditions": 1
}
```

### `inspect_problem(domain, problem, parser?)` -> structured JSON

Returns the problem's name, objects with types, initial state predicates, goal conditions, and counts.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `domain`  | Yes | PDDL domain content string or absolute file path |
| `problem` | Yes | PDDL problem content string or absolute file path |
| `parser`  | No | `"pddl-plus-parser"`, `"unified-planning"`, or null (auto-select with fallback) |

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

### `check_applicable(domain, problem, state, action, parser?)` -> applicability report

Checks whether a grounded action is applicable in a given state. Reports which preconditions are satisfied/unsatisfied and what effects would be applied.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `domain`  | Yes | PDDL domain content string or absolute file path |
| `problem` | Yes | PDDL problem content string or absolute file path |
| `state`   | Yes | `"initial"` or JSON array of predicate strings |
| `action`  | Yes | Grounded action call, e.g. `"(pick-up a)"` |
| `parser`  | No | `"pddl-plus-parser"`, `"unified-planning"`, or null (auto-select with fallback) |

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

### `get_trajectory(domain, problem, plan, parser?)` -> trajectory JSON

Parses domain and problem, simulates plan step-by-step, returns full state-action-state trajectory.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `domain`  | Yes | PDDL domain content string or absolute file path |
| `problem` | Yes | PDDL problem content string or absolute file path |
| `plan`    | Yes | Plan content (one action per line) or absolute file path |
| `parser`  | No | `"pddl-plus-parser"`, `"unified-planning"`, or null (auto-select with fallback) |

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

### `normalize_pddl(content, domain?, output_format?)` -> unified JSON

Parses PDDL content (domain or problem) into a unified structured JSON representation. Bridges both parser backends into a common form.

- **Domain content**: full domain structure (types, predicates, actions)
- **Problem content + domain**: full validated problem structure (objects, init, goal)
- **Problem content, no domain**: lightweight parse — extracts objects, init, goal without validation

| Parameter | Required | Description |
|-----------|----------|-------------|
| `content` | Yes | PDDL domain or problem content string |
| `domain`  | No | Domain content/path. Required for full problem parsing; without it, problem parsing is partial |
| `output_format` | No | `"json"` (default) for structured JSON, `"pddl"` for normalized PDDL text (domain only) |

**Returns (domain):**
```json
{"valid": true, "type": "domain", "normalized": {"name": "bw", "types": {...}, ...}, "warnings": []}
```

**Returns (problem + domain):**
```json
{"valid": true, "type": "problem", "normalized": {"name": "bw1", "objects": [...], "init": [...], "goal": [...], "parser_used": "..."}, "warnings": []}
```

**Returns (problem, no domain):**
```json
{"valid": true, "type": "problem", "normalized": {"name": "bw1", "objects": [...], "init": [...], "goal": [...]}, "warnings": ["Parsed without domain..."]}
```

### `get_applicable_actions(domain, problem, state, max_results, parser?)` -> action list

Enumerates all applicable grounded actions in a given state.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `domain`  | Yes | PDDL domain content string or absolute file path |
| `problem` | Yes | PDDL problem content string or absolute file path |
| `state`   | No | `"initial"` (default) or JSON array of predicate strings |
| `max_results` | No | Maximum results to return (default: 50) |
| `parser`  | No | `"pddl-plus-parser"`, `"unified-planning"`, or null (auto-select with fallback) |

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
