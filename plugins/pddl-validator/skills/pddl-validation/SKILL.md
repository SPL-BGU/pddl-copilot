---
name: pddl-validation
description: Activates when the user asks to write, create, edit, fix, or debug PDDL domain or problem files, or check if a plan is correct.
allowed-tools: mcp__pddl-validator__validate_domain, mcp__pddl-validator__validate_problem, mcp__pddl-validator__validate_plan, mcp__pddl-validator__get_state_transition
---

## Rules for PDDL authoring and validation

### Every PDDL file you create or edit MUST be validated

After writing or modifying any PDDL:
1. Pick the right tool based on what you have in hand:
   - Domain only → `validate_domain(domain=...)`
   - Domain + problem (no plan) → `validate_problem(domain=..., problem=...)`
   - Domain + problem + plan → `validate_plan(domain=..., problem=..., plan=...)`
2. If errors: fix the PDDL, validate again
3. Only declare the PDDL correct after the validator confirms it

Do NOT tell the user the PDDL is correct based on your own analysis alone.

### Available tools

- `validate_domain(domain, verbose?)` — Validates a PDDL domain's syntax, types, and structural consistency (calls pyvalidator's `validate_syntax(domain, None)`). NOT a lexical-only check — covers type-hierarchy soundness, predicate arity, and section nesting. Default `verbose=True` returns `{"valid": bool, "status": str, "report": str, "details": dict}`. With `verbose=False`, drops `details` only.
- `validate_problem(domain, problem, verbose?)` — Validates that a PDDL problem is consistent with its domain (objects, predicates, types resolve). Does NOT validate a plan. Same return shape as `validate_domain`.
- `validate_plan(domain, problem, plan, verbose?)` — Executes a plan against the (domain, problem) and reports whether it reaches the goal. The `valid` field reflects **plan correctness** (preconditions held + goal satisfied), not just syntax. Empty plan `[]` is valid input — represents the empty plan, correct when init already satisfies goal. Same return shape as `validate_domain` plus details on per-step failures.
- `get_state_transition(domain, problem, plan, verbose?)` — Simulates plan execution step-by-step. Use to debug or inspect intermediate states. For a PASS/FAIL verdict, use `validate_plan` instead — it's cheaper and returns a flat shape. Default `verbose=True` returns `{"valid": bool, "report": str, "steps": list, "trajectory": list, "details": dict}`. With `verbose=False`, drops **both** `report` and `details`.

### These tools accept PDDL content strings OR file paths

You can pass either:
- **Inline PDDL content** directly as a string (e.g., the full `(define (domain ...) ...)` text)
- **File paths** to existing `.pddl` files on disk (absolute or relative paths)

For `plan`, you can additionally pass a `list[str]` of action lines.

### Response format

The three `validate_*` tools return:
- `valid` — boolean. For `validate_domain`/`validate_problem`, reflects syntax/consistency. For `validate_plan`, reflects plan correctness.
- `status` — one of `VALID`, `INVALID`, `SYNTAX_ERROR`, `STRUCTURE_ERROR`.
- `report` — human-readable text summary.
- `details` (verbose=True only) — full structured validation result.

`get_state_transition` returns `valid` + `steps[]` + `trajectory[]` (and `report` + `details` if verbose=True). Invalid steps include per-precondition failure diagnostics with current values and deficit amounts.

### `verbose=False` (size-sensitive callers)

Use `verbose=False` when the caller has a tight context window (e.g., small local models) and the heavyweight fields would cause truncation.

The slim shapes are **asymmetric by intent**, matching each tool's information geometry:
- `validate_domain` / `validate_problem` / `validate_plan` slim: drops `details` only. `report` stays — it is the primary human-readable summary; removing it would leave only a boolean and a status string.
- `get_state_transition` slim: drops **both** `report` and `details`. `steps[]` (per-step action, status, changes, unsatisfied preconditions) and `trajectory[]` (boolean/numeric fluents at each state) already encode the structured content that `report` narrates in prose; a text echo is redundant.

Default (`verbose=True`) preserves the full shape.

### If a tool returns errors

Check that the PDDL content is well-formed. Common issues:
1. Missing requirements declarations (e.g., `:numeric-fluents`)
2. Undeclared types, predicates, or objects
3. Parameter count mismatches
