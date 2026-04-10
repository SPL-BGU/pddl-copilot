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

- `validate_pddl_syntax(domain, problem?, plan?)` — Validates PDDL syntax, problem consistency, and plan correctness. Returns `{"valid": bool, "status": str, "report": str, "details": dict}`.
- `get_state_transition(domain, problem, plan)` — Simulates plan execution step-by-step. Returns `{"valid": bool, "report": str, "steps": list, "trajectory": list, "details": dict}`.

### These tools accept PDDL content strings OR file paths

You can pass either:
- **Inline PDDL content** directly as a string (e.g., the full `(define (domain ...) ...)` text)
- **File paths** to existing `.pddl` files on disk (absolute or relative paths)

### Response format

Both tools return structured JSON with:
- `valid` — boolean indicating plan/syntax validity
- `status` — one of `VALID`, `INVALID`, `SYNTAX_ERROR`, `STRUCTURE_ERROR`
- `report` — human-readable text summary
- `details` — full structured validation result (phases, steps, precondition failures, numeric deficits)

For invalid plans, `details` includes per-precondition failure diagnostics with current values and deficit amounts.

### If a tool returns errors:

Check that the PDDL content is well-formed. Common issues:
1. Missing requirements declarations (e.g., `:numeric-fluents`)
2. Undeclared types, predicates, or objects
3. Parameter count mismatches
