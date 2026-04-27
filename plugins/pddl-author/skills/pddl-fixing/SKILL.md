---
name: pddl-fixing
description: Use when the user has a draft PDDL domain plus a description of intent and at least one anchor problem to test against, and wants an iterative fix-loop that runs parse → validate-syntax → solve → validate-plan → trajectory-check until all pass or the loop escalates to a human. Use this when /pddl-authoring produced a draft that fails validation, or when the user reports "this domain doesn't behave as I described".
allowed-tools: mcp__pddl-validator__validate_pddl_syntax, mcp__pddl-validator__get_state_transition, mcp__pddl-parser__normalize_pddl, mcp__pddl-parser__inspect_domain, mcp__pddl-parser__inspect_problem, mcp__pddl-parser__get_trajectory, mcp__pddl-solver__classic_planner, mcp__pddl-solver__numeric_planner
---

## CRITICAL RULES — zero exceptions

### The anchor problem is the ground truth

This skill **requires** at least one problem file (or inline PDDL) that represents a known scenario the user expects the domain to solve. Without it, you have no functional ground truth and cannot prove the domain models the description.

If the user has not provided an anchor problem:
1. Ask for one. A small problem (3–5 objects, single goal) is enough.
2. If the user cannot provide one, offer to draft one from their description, **then pause and ask them to confirm it represents intended behavior** before treating it as ground truth. Do not invent and proceed silently.

### You CANNOT plan, validate, or simulate state in your head

Every check is delegated to a tool. Never "manually verify" a precondition holds, never "trace" a plan mentally. If a tool is unavailable, report that limitation explicitly to the user.

### Stop after 5 iterations

If the loop has not converged after 5 iterations, **stop** and escalate to the user. Report:
- the latest PDDL,
- the most recent failure,
- the diffs you tried,
- what you suspect the underlying intent mismatch is.

Do not loop forever. Human feedback breaks ambiguity that automation cannot.

## The fix loop

Inputs you must collect before starting:
- `domain` — the draft PDDL domain (string or path)
- `description` — the user's natural-language intent
- `problem` — at least one anchor problem (string or path)
- `expected_outcome` (optional) — "the planner should find a plan" / "no plan should exist" / "the plan should include action X"

### Iteration steps (run in order, stop on first failure and fix before continuing)

1. **Parse** — `normalize_pddl(content=domain)`. If it fails, the PDDL is malformed; fix syntax based on the error message. Re-run.
2. **Validate syntax** — `validate_pddl_syntax(domain=domain, problem=problem)`. If `valid=False`, the diagnostic in `report` / `details` tells you what's structurally wrong. Fix and re-run.
3. **Plan** — choose planner by reading the domain:
   - has `:functions` / `increase` / `decrease` → `numeric_planner(domain, problem)`
   - else → `classic_planner(domain, problem)`
   Then act on the result:
   - planner returned a plan AND `expected_outcome` is "no plan should exist" → the domain is too permissive; tighten preconditions of the actions in the returned plan.
   - planner returned no plan AND `expected_outcome` is "a plan should exist" → the domain is too restrictive; loosen preconditions or add a missing action. Use `inspect_domain` and `get_applicable_actions` (if available) to see what's reachable from the initial state.
   - planner errored → read the error verbatim; usually a domain issue (undeclared predicate, type mismatch).
4. **Validate the plan** — if a plan was returned: `validate_pddl_syntax(domain=domain, problem=problem, plan=plan)`. This is the strongest functional check: the planner found *something*, but the validator confirms each step's preconditions actually hold under the domain's semantics. If `valid=False`, the planner and validator disagree — almost always a domain bug (effects not modeled symmetrically with preconditions, or a typo in a predicate name). Fix the domain.
5. **Trajectory check** — `get_trajectory(domain, problem, plan)` and `get_state_transition(domain, problem, plan)`. Compare the final state against the user's `expected_outcome` description. If the plan reaches the goal but does so by exploiting an unintended action, the domain has a semantic bug — flag it to the user before "fixing" silently (this is the case where the loop should escalate).
6. **Done** — all five steps pass and the trajectory matches intent. Report:
   - final domain PDDL,
   - the plan that solved the anchor problem,
   - the trajectory summary,
   - which iterations changed what (one-line diff per iteration).

### Recording each iteration

For each iteration, write **one line** in your reply summarizing:
> `Iter N: failed at step <step>. Diagnosis: <one sentence>. Edit applied: <one sentence>.`

This gives the user a readable audit trail without overwhelming them.

## Tools you may call

- `normalize_pddl` (pddl-parser) — parse check.
- `validate_pddl_syntax` (pddl-validator) — syntax + plan validation.
- `inspect_domain`, `inspect_problem` (pddl-parser) — read-only structure.
- `get_trajectory` (pddl-parser) — step-by-step state-action-state trace.
- `get_state_transition` (pddl-validator) — alternate trajectory view with precondition diagnostics on failure.
- `classic_planner` (pddl-solver) — Fast Downward.
- `numeric_planner` (pddl-solver) — ENHSP. Requires Java 17+.

You may pass either inline PDDL strings or absolute file paths to all of these.

## What you MUST NOT do

- Do NOT proceed without an anchor problem. Ask first.
- Do NOT alter the anchor problem mid-loop to make a buggy domain "pass". The anchor is fixed; only the domain changes (unless the user explicitly says the problem itself is wrong).
- Do NOT make multiple unrelated edits in one iteration — fix one diagnosed issue per iteration so the audit trail is meaningful.
- Do NOT silently exceed 5 iterations. Escalate.
- Do NOT mark the domain "correct" without the trajectory check confirming the user's described outcome. A plan that the validator accepts but achieves the goal via an unintended pathway is a bug, not a fix.

## If a sibling plugin's tool is missing

This skill **requires** all three sibling plugins (validator, parser, solver). If any is missing:
- pddl-validator missing → cannot run steps 2, 4, 5 (partial). Report to user; offer to run a degraded loop using only parser + solver.
- pddl-parser missing → cannot run steps 1, 5 (partial). Report; loop is too weak to be useful — refuse and ask the user to install it.
- pddl-solver missing → cannot run step 3. The loop becomes a syntax-only check, equivalent to `pddl-authoring`. Tell the user and switch to that skill instead.

## Output format

End the loop with:
1. Final domain PDDL in a fenced code block.
2. Anchor problem PDDL (echoed back, unmodified) in a fenced code block.
3. Plan that solved the anchor problem.
4. One-line per-iteration audit trail.
5. Status: `CONVERGED` / `ESCALATED — N iterations exhausted` / `BLOCKED — missing tool: <name>`.
