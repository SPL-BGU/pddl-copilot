---
name: pddl-validation
description: Activates when the user asks to write, create, edit, fix, or debug PDDL domain or problem files, or check if a plan is correct.
allowed-tools: mcp__pddl-validator__validate_pddl_syntax, mcp__pddl-validator__get_state_transition
---

## Rules for PDDL authoring and validation

### Every PDDL file you create or edit MUST be validated

After writing or modifying any PDDL:
1. Call `validate_pddl_syntax(domain="(define (domain ...) ...)", problem="(define (problem ...) ...)")` — you can pass content strings directly, or file paths
2. If errors: fix the PDDL, validate again
3. Only declare the PDDL correct after the validator confirms it

Do NOT tell the user the PDDL is correct based on your own analysis alone.

### Available tools:

- `validate_pddl_syntax(domain, problem?, plan?, verbose?)` — Validates PDDL syntax, problem consistency, and plan correctness. Default `verbose=True` returns `{"valid": bool, "status": str, "report": str, "details": dict}`. With `verbose=False`, drops `details` only: `{"valid": bool, "status": str, "report": str}`.
- `get_state_transition(domain, problem, plan, verbose?)` — Simulates plan execution step-by-step. Default `verbose=True` returns `{"valid": bool, "report": str, "steps": list, "trajectory": list, "details": dict}`. With `verbose=False`, drops both `report` and `details`: `{"valid": bool, "steps": list, "trajectory": list}` — `steps` and `trajectory` already carry the structured content that `report` narrates in prose.

### These tools accept PDDL content strings OR file paths

You can pass either:
- **Inline PDDL content** directly as a string (e.g., the full `(define (domain ...) ...)` text)
- **File paths** to existing `.pddl` files on disk (absolute or relative paths)

### Response format

Both tools return structured JSON with:
- `valid` — boolean indicating plan/syntax validity
- `status` — one of `VALID`, `INVALID`, `SYNTAX_ERROR`, `STRUCTURE_ERROR` (present on `validate_pddl_syntax`; `get_state_transition` exposes the same outcome through `valid` + `steps`/`trajectory`)
- `report` — human-readable text summary
- `details` — full structured validation result (phases, steps, precondition failures, numeric deficits)

For invalid plans, `details` includes per-precondition failure diagnostics with current values and deficit amounts.

### `verbose=False` (size-sensitive callers)

Use `verbose=False` when the caller has a tight context window (e.g., small local models) and the heavyweight fields would cause truncation.

The slim shapes are **asymmetric by intent**, matching each tool's information geometry:
- `validate_pddl_syntax` slim: drops `details` only. `report` stays — it is the primary human-readable summary; removing it would leave only a boolean and a status string.
- `get_state_transition` slim: drops **both** `report` and `details`. `steps[]` (per-step action, status, changes, unsatisfied preconditions) and `trajectory[]` (boolean/numeric fluents at each state) already encode the structured content that `report` narrates in prose; a text echo is redundant.

Default (`verbose=True`) preserves the full shape and is backward-compatible.

### If a tool returns errors:

Check that the PDDL content is well-formed. Common issues:
1. Missing requirements declarations (e.g., `:numeric-fluents`)
2. Undeclared types, predicates, or objects
3. Parameter count mismatches
