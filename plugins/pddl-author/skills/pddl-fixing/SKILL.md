---
name: pddl-fixing
description: Use when the user has a draft PDDL domain plus a description of intent and at least one anchor problem to test against, and wants an iterative fix-loop that runs parse → validate-syntax → solve → validate-plan → trajectory-check until all pass or the loop escalates to a human. Use this when /pddl-authoring produced a draft that fails validation, or when the user reports "this domain doesn't behave as I described".
allowed-tools: mcp__pddl-validator__validate_pddl_syntax, mcp__pddl-validator__get_state_transition, mcp__pddl-parser__normalize_pddl, mcp__pddl-parser__inspect_domain, mcp__pddl-parser__inspect_problem, mcp__pddl-parser__get_trajectory, mcp__pddl-parser__get_applicable_actions, mcp__pddl-parser__check_applicable, mcp__pddl-solver__classic_planner, mcp__pddl-solver__numeric_planner
---

## CRITICAL RULES — zero exceptions

### The intent scenarios are the ground truth

This skill **requires** structured intent scenarios — at minimum one POSITIVE scenario (anchor problem + expected goal-reachability) and ideally one or more NEGATIVE scenarios (anchor problem + "no plan should exist" because of an invariant or forbidden behavior). Without scenarios you have no falsifiable predicate for "the domain models the description" — only a free-text description that cannot be checked.

If the user has not provided structured scenarios:
1. Ask for them. The format is: *"given problem P, a plan should / should not exist. If a plan exists it should reach state S (and optionally include action A)."*
2. If the user used `/pddl-authoring` first, the contract already lists scenarios — pull them in directly.
3. If the user cannot provide them, offer to draft them from their description, **then pause and ask them to confirm before treating as ground truth**. Do not invent and proceed silently.

Negative scenarios are strongly recommended — they catch over-permissive domains that the planner happily solves but the validator cannot flag as wrong.

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
- `intent_scenarios` — structured (preferably from `/pddl-authoring`):
  - **POSITIVE**: anchor problem + expected outcome ("a plan must exist", optionally "must reach state S" or "must include action X").
  - **NEGATIVE**: anchor problem where you expect "no plan should exist" because of an invariant or forbidden behavior.
  At minimum: one positive scenario with an anchor problem.
- `description` (optional) — the user's natural-language intent, used only to disambiguate when scenarios conflict or to draft fresh scenarios when the user cannot supply them.

### Iteration steps (run in order, stop on first failure and fix before continuing)

1. **Parse** — `normalize_pddl(content=domain)`. If it fails, the PDDL is malformed; fix syntax based on the error message. Re-run.
2. **Validate syntax** — `validate_pddl_syntax(domain=domain, problem=problem)`. If `valid=False`, the diagnostic in `report` / `details` tells you what's structurally wrong. Fix and re-run.
3. **Plan against each scenario** — for every scenario in `intent_scenarios`, in order:
   - Choose the planner by reading the domain: has `:functions` / `increase` / `decrease` → `numeric_planner(domain, problem)`; else → `classic_planner(domain, problem)`.
   - Run it against the scenario's anchor problem and check the verdict against the scenario's expected outcome:
     - **POSITIVE expected, planner returned no plan** → domain too restrictive. Use `inspect_domain` and `get_applicable_actions` to see what's reachable from the initial state; loosen preconditions or add the missing action.
     - **NEGATIVE expected, planner returned a plan** → domain too permissive. Tighten preconditions of the actions in the returned plan; the plan that "succeeded" exposes the leaking path.
     - **Planner errored** → read the error verbatim; usually a domain issue (undeclared predicate, type mismatch).
   Stop at the **first** failing scenario, fix the diagnosed issue, then restart the loop. Do not chase multiple scenario failures in one edit.
4. **Validate the plan** — if a plan was returned: `validate_pddl_syntax(domain=domain, problem=problem, plan=plan)`. This is the strongest functional check: the planner found *something*, but the validator confirms each step's preconditions actually hold under the domain's semantics. If `valid=False`, the planner and validator disagree — almost always a domain bug (effects not modeled symmetrically with preconditions, or a typo in a predicate name). Fix the domain.
5. **Trajectory check against scenarios** — `get_trajectory(domain, problem, plan)` and `get_state_transition(domain, problem, plan)`. For each POSITIVE scenario, confirm the trajectory's final state satisfies the scenario's expected goal predicates; if the scenario named "must include action X," confirm X appears in the plan. If the plan reaches the goal by using an action that the contract listed as forbidden, the domain has a semantic bug — flag it to the user before "fixing" silently (this is when the loop should escalate to human review).
6. **Done** — every scenario converges: every POSITIVE yields a valid plan whose trajectory satisfies its expected outcome, and every NEGATIVE yields no plan. Report:
   - final domain PDDL,
   - the plans that solved each positive scenario (and the verdict for each negative scenario),
   - trajectory summary for at least one positive scenario,
   - which iterations changed what (one-line diff per iteration).

### Recording each iteration

For each iteration, write **one line** in your reply summarizing:
> `Iter N: failed at step <step>. Diagnosis: <one sentence>. Edit applied: <one sentence>.`

This gives the user a readable audit trail without overwhelming them.

## Tools you may call

- `normalize_pddl` (pddl-parser) — parse check.
- `validate_pddl_syntax` (pddl-validator) — syntax + plan validation.
- `inspect_domain`, `inspect_problem` (pddl-parser) — read-only structure.
- `get_applicable_actions` (pddl-parser) — list legal moves from a state; useful when diagnosing "domain too restrictive" in step 3.
- `check_applicable` (pddl-parser) — test a specific action in a specific state; useful for pinpointing which precondition blocks an expected action.
- `get_trajectory` (pddl-parser) — step-by-step state-action-state trace.
- `get_state_transition` (pddl-validator) — alternate trajectory view with precondition diagnostics on failure.
- `classic_planner` (pddl-solver) — Fast Downward.
- `numeric_planner` (pddl-solver) — ENHSP. Requires Java 17+.

You may pass either inline PDDL strings or absolute file paths to all of these.

## What you MUST NOT do

- Do NOT proceed without at least one positive scenario and its anchor problem. Ask first.
- Do NOT alter scenario problems mid-loop to make a buggy domain "pass". Scenarios are fixed; only the domain changes (unless the user explicitly says the scenario itself is wrong).
- Do NOT make multiple unrelated edits in one iteration — fix one diagnosed issue per iteration so the audit trail is meaningful.
- Do NOT cherry-pick scenarios. If you fix scenario A and the edit breaks scenario B, that's a regression — note it in the audit and address both before claiming convergence.
- Do NOT silently exceed 5 iterations. Escalate.
- Do NOT mark the domain "correct" without the trajectory check satisfying every positive scenario AND every negative scenario yielding no plan. A plan that the validator accepts but achieves the goal via an action listed as forbidden in the contract is a bug, not a fix.

## If a sibling plugin's tool is missing

This skill **requires** all three sibling plugins (validator, parser, solver). If any is missing:
- pddl-validator missing → cannot run steps 2, 4, 5 (partial). Report to user; offer to run a degraded loop using only parser + solver.
- pddl-parser missing → cannot run steps 1, 5 (partial). Report; loop is too weak to be useful — refuse and ask the user to install it.
- pddl-solver missing → cannot run step 3. The loop becomes a syntax-only check, equivalent to `pddl-authoring`. Tell the user and switch to that skill instead.

## Output format

End the loop with:
1. Final domain PDDL in a fenced code block.
2. Scenario set: each scenario's problem PDDL echoed back unmodified in a fenced code block, labeled `POSITIVE` / `NEGATIVE`.
3. For each positive scenario: the plan that solved it. For each negative scenario: the verdict (`no plan exists, as expected` or `LEAKED — plan was: …`).
4. One-line per-iteration audit trail.
5. Status: `CONVERGED` / `ESCALATED — N iterations exhausted` / `BLOCKED — missing tool: <name>` / `REGRESSED — scenario <name> broke at iteration N`.
