---
name: pddl-authoring
description: Use when the user asks to draft, generate, write, or translate a natural-language description into a PDDL domain or problem from scratch, or to revise an existing PDDL draft based on human feedback (add an action, change a precondition, rename a predicate, etc.). NOT for fixing parser/validator errors — use pddl-fixing for that.
allowed-tools: mcp__pddl-validator__validate_pddl_syntax, mcp__pddl-parser__normalize_pddl, mcp__pddl-parser__inspect_domain, mcp__pddl-parser__inspect_problem
---

## CRITICAL RULES — zero exceptions

### You MUST validate every PDDL file you produce before reporting it as done

After writing or editing a domain or problem:
1. Call `normalize_pddl(content=...)` to confirm it parses.
2. Call `validate_pddl_syntax(domain=..., problem=...)` to confirm syntactic + structural validity.
3. Only report the draft to the user if both succeed.
4. If either fails: do **not** silently retry forever. Hand off to the `pddl-fixing` skill (tell the user: "syntax errors remain — switching to /pddl-fixing").

### You are NOT a planner and NOT a validator

This skill produces drafts. It does **not** prove correctness. Functional correctness against an intent is the job of `pddl-fixing`. Do not claim a domain "models the description correctly" based on your own reading.

### Do not invent semantics

If the user's description is ambiguous (e.g., "objects can be moved" — by whom? in what state?), ask one clarifying question before authoring. Do not guess at hidden constraints. Better to surface ambiguity than to bake a wrong assumption into preconditions.

## Two entry modes

### Mode A — blank-start authoring

User provides a natural-language description; no prior PDDL exists.

Workflow:
1. **Restate the domain** in 3–5 bullets: types, predicates you'll introduce, actions, key invariants. Show this to the user.
2. **Pause for confirmation** unless the user said "just do it" or auto mode is active. Restating catches misunderstandings before code.
3. **Draft the domain** as a single PDDL string. Use `:requirements` minimally — declare only what you actually use (`:typing`, `:negative-preconditions`, `:numeric-fluents`, etc.).
4. **Validate**: `normalize_pddl(content=domain)` then `validate_pddl_syntax(domain=domain)`.
5. **If the user also asked for an example problem**, draft it after the domain validates, then re-validate with both.
6. **Report**: the draft PDDL plus the validator status. Suggest `/pddl-fixing` if the user wants the fix-loop with planner verification.

### Mode B — feedback-driven revision

User provides existing PDDL plus a description of the change they want.

Workflow:
1. **Read the current PDDL** (use `inspect_domain` / `inspect_problem` if helpful — gives you grounded actions, types, predicates).
2. **State the diff in plain language**: "I will add action `unload`, change precondition X of action Y, …". Pause for confirmation if the change is non-trivial (>3 edits, or alters existing action semantics).
3. **Apply the edit** to the PDDL string. Keep all unrelated code byte-identical — do not "clean up" while editing.
4. **Validate**: `normalize_pddl` then `validate_pddl_syntax`.
5. **Report** the new draft plus the validator status.

## Tools you may call

- `normalize_pddl(content, domain?, output_format?)` (pddl-parser) — quick parse check; returns structured JSON or raises a parse error.
- `validate_pddl_syntax(domain, problem?, plan?, verbose?)` (pddl-validator) — full syntax + structural validation.
- `inspect_domain(domain, problem?, parser?)` (pddl-parser) — read-only structure of an existing draft (actions, predicates, types).
- `inspect_problem(domain, problem, parser?)` (pddl-parser) — read-only structure of an existing problem.

You may pass either inline PDDL strings or absolute file paths to all of these.

## What you MUST NOT do

- Do NOT skip validation. A draft that hasn't passed `validate_pddl_syntax` is not a draft — it's a guess.
- Do NOT call planners (`classic_planner` / `numeric_planner`) from this skill. Planning is the fix-loop's job.
- Do NOT auto-fix repeatedly without bound. After one validate-fix cycle, if errors remain, hand off to `pddl-fixing` and tell the user.
- Do NOT add `:requirements` you don't use. Each requirement implies a feature; redundant ones confuse downstream tools.

## If a sibling plugin's tool is missing

If `validate_pddl_syntax` or `normalize_pddl` is not available (the user did not install pddl-validator / pddl-parser), do not silently produce unvalidated PDDL. Tell the user:

> "I drafted the PDDL but cannot validate it because `pddl-validator` / `pddl-parser` is not installed. Install them and re-run, or accept the draft as unverified."

## Output format

Always return:
1. The full PDDL content (domain, and problem if requested), in fenced code blocks.
2. A short status line: `Validation: PASSED` / `Validation: FAILED — see report below` / `Validation: SKIPPED — pddl-validator not installed`.
3. Suggested next step (e.g., `/pddl-fixing` if validation passed but the user wants a planner-backed correctness check).
