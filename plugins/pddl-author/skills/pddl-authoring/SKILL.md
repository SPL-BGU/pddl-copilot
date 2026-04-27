---
name: pddl-authoring
description: Use when the user asks to draft, generate, write, or translate a natural-language description into a PDDL domain or problem from scratch, or to revise an existing PDDL draft based on human feedback (add an action, change a precondition, rename a predicate, etc.). NOT for fixing parser/validator errors — use pddl-fixing for that.
allowed-tools: mcp__pddl-validator__validate_pddl_syntax, mcp__pddl-parser__normalize_pddl, mcp__pddl-parser__inspect_domain, mcp__pddl-parser__inspect_problem, mcp__pddl-parser__get_applicable_actions, mcp__pddl-parser__check_applicable
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

The intent contract (see Mode A step 1) is your defense against guessing. If the user's description is ambiguous (e.g., "objects can be moved" — by whom? in what state?), the ambiguity should appear as a flagged or guessed cell in the contract — surface it there rather than baking a wrong assumption into preconditions. If a guessed cell remains after the user reviews the contract, ask one clarifying question before drafting PDDL.

## Two entry modes

### Mode A — blank-start authoring

User provides a natural-language description; no prior PDDL exists.

Workflow:
1. **Build the intent contract** — propose a structured table the user can audit cell-by-cell:
   - **Types** — name → one-line meaning
   - **Predicates** — `(name ?args)` → one-line meaning
   - **Numeric fluents** (only if needed)
   - **Actions** — `name | params | when-can-fire (preconditions in plain words) | what-changes (effects in plain words)`
   - **Invariants** — properties that must always hold
   - **Forbidden behaviors** — things the user expects to NOT be possible
   - **Intent scenarios** — at least one POSITIVE ("from state X a plan must reach Y") and one NEGATIVE ("from state X no plan should exist") that pin down intent as falsifiable predicates. These also seed `/pddl-fixing`.
2. **Pause for confirmation** unless the user said "just do it" or auto mode is active. Even in auto mode, always *show* the contract so the user can interrupt — the user accepts, edits, or corrects cells in one turn, never a multi-question interview.
3. **Draft the domain** as a single PDDL string. Mirror the contract: every action's precondition/effect comes from its row in the action table. Use `:requirements` minimally — declare only what you actually use (`:typing`, `:negative-preconditions`, `:numeric-fluents`, etc.).
4. **Validate syntax**: `normalize_pddl(content=domain)` then `validate_pddl_syntax(domain=domain)`.
5. **Tool-grounded intent verification** (strongly recommended; requires a tiny example problem):
   - If the user did not supply a problem, draft one that exercises the positive and negative scenarios and ask them to confirm it represents intent before treating it as ground truth.
   - Call `inspect_domain(domain, problem)` — confirm grounded action signatures match the contract's action table.
   - Call `get_applicable_actions(domain, problem, "initial")` — show the user the legal moves from the initial state and ask "does this match your intuition?" Surface any surprises (an action firing when the contract said it shouldn't, or a missing action the contract expected).
   - For each forbidden behavior: construct the smallest state where the forbidden action *would* fire if the domain were broken; call `check_applicable(...)` and confirm the result is "not applicable."
6. **Report**: the contract, the draft PDDL (and problem, if drafted), validator status, and the tool-verification verdicts (matched / surprises). Suggest `/pddl-fixing` to run the planner against the positive and negative scenarios.

### Mode B — feedback-driven revision

User provides existing PDDL plus a description of the change they want.

Workflow:
1. **Project the current PDDL into the intent contract**: call `inspect_domain` (and `inspect_problem` if a problem is available), then render the same table format from Mode A — types, predicates, actions, invariants. This is the baseline.
2. **State the proposed delta as a contract diff** — show only the cells changing (or the rows being added / removed). Pause for confirmation if the change is non-trivial (>3 cell changes, or alters existing action semantics). For renames-only, no confirmation needed.
3. **Apply the edit** to the PDDL string. Keep all unrelated code byte-identical — do not "clean up" while editing.
4. **Validate syntax**: `normalize_pddl` then `validate_pddl_syntax`.
5. **Tool-grounded re-verification** (if a problem is available): call `inspect_domain` again to confirm the new grounded signatures match the updated contract; spot-check applicability on at least one scenario the user named.
6. **Report** the contract diff, the new draft, and the validator status.

## Tools you may call

- `normalize_pddl(content, domain?, output_format?)` (pddl-parser) — quick parse check; returns structured JSON or raises a parse error.
- `validate_pddl_syntax(domain, problem?, plan?, verbose?)` (pddl-validator) — full syntax + structural validation.
- `inspect_domain(domain, problem?, parser?)` (pddl-parser) — read-only structure of an existing draft (actions, predicates, types).
- `inspect_problem(domain, problem, parser?)` (pddl-parser) — read-only structure of an existing problem.
- `get_applicable_actions(domain, problem, state?, max_results?, parser?)` (pddl-parser) — list legal moves from a state. Used in Mode A step 5 to show the user what the domain actually permits from the initial state.
- `check_applicable(domain, problem, state, action, parser?)` (pddl-parser) — test whether a specific action fires in a specific state. Used in Mode A step 5 to verify that forbidden behaviors are forbidden.

You may pass either inline PDDL strings or absolute file paths to all of these.

## Worked example (Mode A, compressed)

User: *"I want a domain where a truck delivers packages between locations connected by direct routes."*

LLM proposes the contract:

| section | content |
|---|---|
| types | `truck`, `location`, `package` |
| predicates | `(at ?x ?l)` — object x is at location l. `(in ?p ?t)` — p loaded in t. `(connected ?l1 ?l2)` — direct route. |
| actions | `load(?p ?t ?l)`: truck and package both at l → adds `(in p t)`, removes `(at p l)`. `unload(?p ?t ?l)`: truck at l, p in truck → adds `(at p l)`, removes `(in p t)`. `drive(?t ?l1 ?l2)`: truck at l1, l1 connected to l2 → adds `(at t l2)`, removes `(at t l1)`. |
| invariants | a package is at exactly one location OR in exactly one truck — never both, never neither. |
| forbidden | trucks cannot teleport (drive requires `connected`); packages cannot move on their own. |
| scenarios | **POS**: t1 at A, p1 at A, A connected to B → plan must reach `(at p1 B)`. **NEG**: same setup but no `(connected A B)` → no plan should exist. |

User: *"looks right — but rename `connected` to `road-between` and make it symmetric in init (both directions)."*

LLM updates the contract (one cell changed), drafts the PDDL, runs `normalize_pddl` + `validate_pddl_syntax` (PASSED), then:

- `inspect_domain` → grounded signatures match the action table.
- `get_applicable_actions(state="initial")` → returns `(drive t1 A B)`, `(load p1 t1 A)`. Matches expectation.
- `check_applicable((drive t1 A B), state without (road-between A B))` → not applicable. Forbidden behavior holds.

LLM reports the contract, the PDDL, `Validation: PASSED`, all verdicts matched, the scenarios — and suggests `/pddl-fixing` for full planner-backed verification.

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
1. The **intent contract** (Mode A) or the **contract diff** (Mode B), as compact tables.
2. The full PDDL content (domain, and problem if drafted), in fenced code blocks.
3. A short status line: `Validation: PASSED` / `Validation: FAILED — see report below` / `Validation: SKIPPED — pddl-validator not installed`.
4. **Tool-verification verdicts** (one line per check): e.g. `inspect_domain: matched`, `applicable from initial: matched` / `surprise: <action>`, `forbidden behavior <name>: held` / `leaked`.
5. The intent scenarios in a fenced block, formatted so they can be passed verbatim to `/pddl-fixing`.
6. Suggested next step (e.g., `/pddl-fixing` to run the planner against the scenarios).
