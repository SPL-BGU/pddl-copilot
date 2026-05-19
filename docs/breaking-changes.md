# Breaking Changes — Plugin Interface Migration Log

This document records every interface change in the pddl-copilot plugins that
may affect downstream consumers — most notably the
[`pddl-copilot-experiments`](https://github.com/SPL-BGU/pddl-copilot-experiments)
framework, which pins plugin behavior via its MCP bridge (`pddl_eval/chat.py`).

Each entry names the affected tool, the version that introduced the change,
the nature of the change (`fix` / `additive` / `breaking`), and the
migration step required in consuming code (if any). Add an entry here whenever
a plugin makes a user-visible interface change. Run the experiments-repo
validator (see `tests/` in that repo) after merging any `fix` or `breaking`
entry to confirm the bridge still parses responses correctly.

---

## 2026-05-18 — Tool interface audit fixes

Marketplace `1.2.0 → 1.3.0`. Triggered by the May-2026 tool interface audit.

### pddl-solver `2.1.1 → 2.2.0`

| Tool | Change | Type | Migration |
|---|---|---|---|
| `classic_planner`, `numeric_planner` | `INTERNAL_ERROR` / `UNSUPPORTED_PROBLEM` / `INTERMEDIATE` planner statuses now return `{"error": True, "message": str, "status": str, "log": str, "solve_time": float}` instead of `{"plan": [], "note": "Planner ran but did not find a plan.", ...}`. ENHSP without Java surfaces a clear `"Java runtime not found"` message. | **fix (behavior change)** | Experiments bridge: `_parse_validation_verdict` is not affected (only reads `valid` from the validator). The scoring layer's `_tool_error_seen` already detects `{"error": True}` correctly (`scoring.py`). No migration required, but verify that no run-correctness logic relied on the old empty-plan-plus-note shape. Confirmed reachable as `FR_TOOL_ERROR`. |
| `classic_planner`, `numeric_planner` | Status routing unchanged for `UNSOLVABLE_PROVEN` / `UNSOLVABLE_INCOMPLETELY` (still `{"plan": [], "note": "Problem is unsolvable", "solve_time": float}`) and `TIMEOUT` / `MEMOUT` (still `{"error": True, "message": ...}`). | additive | None. |
| `save_plan` | `plan` parameter typed `list[str]` (was bare `list`). | additive (schema-only) | None. |
| `save_plan` | Docstring revised. Filename pattern is now correctly documented as `plan_<tag>.solution`, where `<tag>` is `name` (when supplied) or a derived/random fragment. `name` is a tag fragment, not a literal-filename override. Behavior is unchanged from prior versions. | doc-only | None. |

### pddl-validator `2.1.1 → 2.2.1`

| Tool | Change | Type | Migration |
|---|---|---|---|
| `validate_pddl_syntax` | When called *without* a plan (domain-only or domain+problem), the `report` text no longer contains the leaked `"Plan is VALID"` / `"Plan is INVALID"` line. The actual fix lives upstream in **pyvalidator 0.1.5** ([SPL-BGU/pyvalidator#1](https://github.com/SPL-BGU/pyvalidator/pull/1)) — the formatter's Goal Check block is now gated on `"execution" in result.phases`. Requirements pin bumped to `pddl-pyvalidator>=0.1.5`. The `valid` boolean and `status` are unaffected. | **fix (behavior change, upstream)** | If any experiment grepped the `report` string for `"Plan is VALID"` to derive a syntax-check verdict, switch to reading `valid` (canonical signal — `_parse_validation_verdict` already does this). Verified: experiments do NOT grep the report for these markers. |
| `validate_pddl_syntax`, `get_state_transition` | `plan` accepts `list[str]` in addition to `str` (content) or `str` (path). Empty list = empty plan, used to validate "init already satisfies goal." | additive | None. Existing string callers unaffected. |
| `validate_pddl_syntax` | Docstring rewrite — three modes now stated explicitly. Tool name retained for backward compatibility (`validate_pddl_syntax` is a heavily-referenced symbol in `pddl-copilot-experiments`). The audit's rename suggestion (`validate_pddl`) was rejected to avoid the cross-repo blast radius. | doc-only | None. |

### pddl-parser `1.4.0 → 1.5.0`

| Tool | Change | Type | Migration |
|---|---|---|---|
| All tools | `parser` parameter typed `Literal["pddl-plus-parser", "unified-planning"]` (was free-form `str`). Misspellings now fail at schema validation rather than at the runtime fallback's "Parser not available" check. Valid values unchanged. | breaking (schema) | None for callers passing valid values. Misspelled callers now get a clearer Pydantic validation error. |
| `normalize_pddl` | `content` parameter now accepts file paths in addition to inline content. Paths are read and dispatched to the same parsing code path. Brings parity with every other tool. | additive | None. |
| `normalize_pddl` | Response now includes a dedicated `errors: list[str]` field separate from `warnings`. Hard parse failures populate `errors`; `warnings` retains the same message for one release as a backward-compat alias. | additive (with deprecation) | New callers should read `errors` for hard failures and `warnings` for soft issues. Old callers reading only `warnings` continue to work. |
| `inspect_domain`, `normalize_pddl` | `types` dict no longer contains the implicit `"object": null` root. Both backends drop it. | **fix (response-shape change)** | If a caller iterated `types` and emitted PDDL `:types` from it, the rendered output now omits the redundant `object` declaration. Re-rendering still produces semantically-equivalent PDDL. |
| `inspect_domain`, `normalize_pddl` | `:requirements` now preserves the order declared in the PDDL source (was alphabetized). | **fix (response-shape change)** | If a caller relied on alphabetical order, switch to explicit `sorted(...)`. Re-rendered PDDL now round-trips the original `:requirements` order. |
| `get_applicable_actions` | Results are sorted lexicographically before truncation. Truncated subsets are now deterministic across backends and runs. | **fix (response-shape change)** | None unless a caller expected a specific (undefined) prior order. |
| `get_trajectory` | `plan` accepts `list[str]` in addition to string/path. | additive | None. |
| `check_applicable`, `get_applicable_actions` | Docstrings now state the closed-world semantic explicitly (predicates not listed in `state` are treated as false). `check_applicable` docstring also clarifies that `would_add`/`would_delete` are returned for diagnosis even when `applicable=false` and are NOT applied. | doc-only | None. |

### Deferred (not in this release)

These audit findings were considered and deliberately deferred — implementing
them would require cross-repo coordination that exceeds the scope of an
interface cleanup:

- **Unify state-serialization formats** across `get_trajectory` (Lisp string),
  `get_state_transition.trajectory` (dict), and
  `diff_states`/`check_applicable`/`get_applicable_actions` (JSON array of
  Lisp strings). `get_state_transition.trajectory` is the byte-equality
  oracle for the experiments `simulate` task
  (`EXPERIMENTS_FLOW.md:145`); any change requires fixture regeneration.
  Track as a separate design discussion before any release.
- **Rename `validate_pddl_syntax` → `validate_pddl`** (or split). Too
  many references across `pddl-copilot-experiments` (CHANGELOG, scoring,
  tests, plan docs). Would require a coordinated rename across both repos.
- **`get_applicable_actions` `hide_no_op` flag.** Optional feature; no
  consumer has asked for it yet.
- **`save_plan.name` true filename override.** Audit asked for `name` to
  drop the `plan_` prefix and `_N` suffix. Behavior is unchanged in this
  release; only the docstring is corrected to describe what actually
  happens. Revisit if a user actually needs literal-filename control.
- **Shrink `validate_pddl_syntax.report` when `verbose=False`.** Audit
  asked for a one-line summary. Bridge currently passes the report through
  unmodified; shrinking it changes what experiments log. Defer.

---

## Recipe for adding entries

When you change a plugin's tool interface:

1. Bump the plugin's `version` in its `marketplace.json` entry (both
   `.claude-plugin/` and `.cursor-plugin/`).
2. Bump the marketplace `metadata.version` in both files.
3. Add a row to this document under a new dated section. State the tool,
   the change, the type (`fix` / `additive` / `breaking` / `doc-only`),
   and the migration step.
4. Add a `## <new-version>` entry to the plugin's `CHANGELOG.md`.
5. Run the affected plugin's `tests/verify.py` to confirm the change.
6. Dispatch the experiments-repo validator (an agent with `cwd` at
   `/Users/omereliyahu/personal/pddl-copilot-experiments`) to verify that
   the experiments framework's bridge and oracles are unaffected.
