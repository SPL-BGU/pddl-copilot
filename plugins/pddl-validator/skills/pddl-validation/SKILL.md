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

- `validate_pddl_syntax(domain, problem?, plan?)` — VAL. Validates PDDL syntax and plans. Returns validation output.
- `get_state_transition(domain, problem, plan)` — Returns VAL verbose output showing state transitions after plan execution.

### These tools accept PDDL content strings OR file paths

You can pass either:
- **Inline PDDL content** directly as a string (e.g., the full `(define (domain ...) ...)` text)
- **File paths** to existing `.pddl` files on disk (absolute host paths are translated to container paths automatically)

### If a tool returns "not found" or connection errors:

Either Docker is not installed, or the image build failed. Tell the user:
1. Make sure Docker is installed: https://docker.com
2. Try manually: `docker build -t pddl-sandbox <repo_root>/docker/`
3. Restart Claude Code
