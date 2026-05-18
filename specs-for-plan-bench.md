# Specs for PlanBench tool-using arm

This file scopes the MCP plugin work that the PlanBench evaluation arm needs from `pddl-copilot`. None of it is required for the **vanilla leaderboard** path (no tools, NL-only prompting through PlanBench's own grader). It is required only for the **tool-using arm** that the PlanBench integration guide explicitly carves out as a distinct method ("LLM-Modulo", see `LLMs-Planning/INTEGRATION.md` §3, Note on tools).

Upstream driver: `pddl-copilot-experiments` branch `planbench-integration` adds the PlanBench engine adapter + cluster wrapper but does **not** invoke any new MCP tool. Once the v2 tool-using arm lands in the experiments repo, it will exercise the tools defined here.

Owner: TBD. Branch on this repo: `planbench-integration` (this branch).

---

## 1. Validator: `validate_plan_structured`

**Why.** PlanBench task **t3 (Plan Verification)** asks the LLM to classify a plan as valid/invalid AND to identify which step failed plus the offending precondition. Today's `validate_pddl_syntax` returns only `{valid, status, report}` — the LLM has to parse `report` (free-text) to extract the step index and failed precondition, which it does unreliably even at 30B+ scale. A structured-failure return lets the tool-using arm score t3's three sub-metrics (`llm_correct_binary`, `llm_correct_w_type`, `llm_correct_w_expl`) without text-extraction noise.

**Contract.**
```jsonc
// New tool, additive to existing validate_pddl_syntax (do not break existing contract).
{
  "name": "validate_plan_structured",
  "inputs": {
    "domain":  "str (PDDL content or path; same shape as validate_pddl_syntax.domain)",
    "problem": "str (required)",
    "plan":    "str (required, newline-separated `(action arg...)` lines)"
  },
  "returns": {
    "valid": "bool",
    "failed_step_index": "int | null  // 0-based; null when valid=true",
    "failed_action":      "str  | null  // e.g. '(unstack a b)'",
    "failed_precondition":"str  | null  // textual rendering of the unmet condition",
    "error_type":         "Literal['unsatisfied_precondition','unknown_action','goal_not_reached','effects_inconsistent'] | null",
    "report":             "str  // verbose pyvalidator text, same as validate_pddl_syntax for callers who still want it"
  }
}
```

**Implementation sketch.** Wrap the same pyvalidator code path used by `validate_pddl_syntax` (plan branch). Inspect pyvalidator's per-step `details` (already populated when `verbose=True` inside the plugin) and project it into the structured shape. Existing experiment bridge's `verbose=False` pin (`MCPPlanner._PINNED_VERBOSE_FALSE`, see `pddl-copilot-experiments/pddl_eval/chat.py`) does NOT apply to this new tool — the structured return is intentionally small (< 1 KB), so callers don't need a `verbose` toggle.

**Plugin isolation.** Lives entirely in `plugins/pddl-validator/server/`. No cross-imports.

**Tests.** Add to `plugins/pddl-validator/tests/verify.sh`: one valid plan (returns `valid=true`, all step/precondition fields null), one invalid plan with a missing precondition (returns `error_type=unsatisfied_precondition`, specific step + precondition strings).

---

## 2. Solver: `optimal_plan`

**Why.** PlanBench task **t2 (Optimal Planning)** grades both validity AND cost-optimality. Our current `classic_planner` returns a satisficing LAMA-first plan; the tool-using arm has no way to recover the *optimal* cost, so any tool-using t2 trial that emits the satisficing plan scores as suboptimal even when valid. An explicit optimal-cost tool fixes this.

**Contract.**
```jsonc
// New tool, additive to existing classic_planner.
{
  "name": "optimal_plan",
  "inputs": {
    "domain":  "str (PDDL content or path)",
    "problem": "str",
    "timeout_s": "int = 120  // wall-clock cap; sweep config overrides via env"
  },
  "returns": {
    "plan":       "list[str] | null",
    "cost":       "int | float | null",
    "is_optimal": "bool",
    "solver":     "str  // 'fast-downward seq-opt-lmcut' on success",
    "solve_time": "float",
    "error":      "bool | null",
    "message":    "str  | null"
  }
}
```

**Implementation sketch.** Use Fast Downward's `--alias seq-opt-lmcut` (A* + LM-cut heuristic). FD is already inside the solver plugin's venv via `up-fast-downward`. The existing `classic_planner` calls FD with LAMA-first; the new tool calls the same FD binary with a different alias. ~30–60 LOC of wrapper + the same timeout / log-tail handling already in place (`PDDL_TIMEOUT`, `PDDL_MAX_LOG_CHARS`).

**Cost semantics.** Cost equals plan length when the domain has no `:action-costs` `(:metric)`; otherwise it's the FD-reported `g-value` at the goal. PlanBench's t2 grader (`Executor/`) uses the same FD-derived cost as ground truth, so cost values will match by construction.

**Plugin isolation.** Lives entirely in `plugins/pddl-solver/server/`. No cross-imports.

**Tests.** Add to `plugins/pddl-solver/tests/verify.sh`: a blocksworld instance where FD's optimal plan is shorter than LAMA-first's; assert `is_optimal=true` and a smaller `cost` than `classic_planner` on the same problem.

---

## 3. Agentic-author MCP exposure — TODO, v2 only

**Status.** The `pddl-author` plugin currently ships as a **skill-only** Claude-Code workflow (`.claude/skills/pddl-author/`, `.claude/skills/pddl-fixer/`). It does not expose an MCP tool surface; the iterative `parse → validate-syntax → solve → validate-plan → trajectory-check` loop is driven by Claude Code reading skill instructions.

**Why this might matter for PlanBench.** None of PlanBench's 10 tasks (t1–t8_3) ask the LLM to author a domain from NL — the domain is always given. So vanilla and tool-using PlanBench do **not** need an agentic-author MCP tool.

**The only scenario that surfaces an author dependency:** an *extension* benchmark beyond PlanBench where the LLM is asked to translate an NL world model into PDDL and then plan over it. That belongs to the planned "Paper 2 autonomous monitoring agent" track (per `pddl-copilot-experiments/.claude/projects/-Users-omereliyahu-personal-pddl-copilot-experiments/memory/project_paper_strategy.md`), not PlanBench v1/v2.

**Action.** **None for the PlanBench arm.** Track here so the next reader knows the gap is intentional. If the Paper-2 agent track later needs an MCP-callable author/fixer loop, open a separate spec — the requirements (streaming progress, async cancellation, multi-minute budgets) differ enough that bolting it onto the existing per-call MCP contract would be a mistake.

---

## 4. Out of scope (call out, don't implement)

- **NL↔PDDL parser tool** for Mystery / Obfuscated PlanBench domains. The PlanBench arm v1 restricts to canonical Blocksworld + Logistics + Depots configs, where domains are presented to the LLM in canonical predicate names (no synonym swap). If a future sweep adds `mystery_blocksworld.yaml` or `obfuscated_*` configs, revisit and either (a) wrap PlanBench's own `utils/pddl_to_text.py` as an MCP tool here, or (b) let the engine adapter call PlanBench's utility directly and skip the MCP round-trip.
- **`save_plan` extensions.** Existing `save_plan` already covers what the t6 (replanning) tool-using flow needs.
- **Numeric planner additions.** None of PlanBench's 10 canonical-domain tasks are numeric.

---

## 5. Sequencing

1. Land §1 (`validate_plan_structured`) — unblocks tool-using t3.
2. Land §2 (`optimal_plan`) — unblocks tool-using t2.
3. Hand control back to `pddl-copilot-experiments` to wire the tool-using engine adapter (engine name `pddl_copilot_tools__<backend>__<model>`).

Each step is an isolated PR on this branch with its own plugin's `verify.sh` extension. Merge order is §1 → §2 → experiments-side wiring; they don't conflict and can be reviewed independently.

---

## 6. What is NOT changing

- Existing `validate_pddl_syntax` contract — including the experiment-bridge `verbose=False` pin (`_PINNED_VERBOSE_FALSE` in `pddl-copilot-experiments/pddl_eval/chat.py`). The new structured tool is additive; existing callers see no shape change.
- Existing `classic_planner` / `numeric_planner` — `optimal_plan` is additive.
- Plugin isolation rule (`.claude/rules/marketplace.md`): no cross-imports between plugins.
- `pddl-author` and `pddl-parser` plugins — untouched for the PlanBench arm.
