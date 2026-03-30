---
name: pddl-parsing
description: Activates when the user asks to generate a trajectory, trace plan execution step by step, inspect structured state transitions, or parse PDDL representations.
allowed-tools: mcp__pddl-parser__get_trajectory
---

# PDDL Parsing Skill

## Rules

1. **Always use the tool** to generate trajectories. Do NOT fabricate state representations — LLMs cannot reliably compute action effects.
2. **Report errors verbatim** from tool output. Common causes: mismatched domain/problem names, actions in the plan not defined in the domain, type mismatches.

## Tools

### `get_trajectory(domain, problem, plan)` -> structured JSON

Parses domain and problem, simulates plan step-by-step, returns full state-action-state trajectory.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `domain`  | Yes | PDDL domain content string or absolute file path |
| `problem` | Yes | PDDL problem content string or absolute file path |
| `plan`    | Yes | Plan content (one action per line) or absolute file path |

**Input formats:**
- Inline content: strings starting with `(`, `;`, or containing `(define ` are treated as PDDL content
- File paths: absolute paths to existing `.pddl` or plan files

**Returns (success):**
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

**Returns (error):**
```json
{"error": true, "message": "description of what went wrong"}
```

## Cross-plugin notes

- If `pddl-solver` is installed, first compute a plan, then use `get_trajectory` to trace it.
- If `pddl-validator` is installed, validate the plan before tracing to catch errors early.
