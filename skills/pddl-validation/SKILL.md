---
name: pddl-validation
description: Activates when the user asks to write, create, edit, fix, or debug PDDL domain or problem files, or check if a plan is correct.
---

## Rules for PDDL authoring and validation

### Every PDDL file you create or edit MUST be validated

After writing or modifying any PDDL:
1. Call `validate_pddl_syntax(domain="(define (domain ...) ...)", problem="(define (problem ...) ...)")` — you can pass content strings directly, or file paths
2. If errors: fix the PDDL, validate again
3. Only declare the PDDL correct after the validator confirms it

Do NOT tell the user the PDDL is correct based on your own analysis alone.
