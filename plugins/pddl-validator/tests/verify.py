#!/usr/bin/env python3
"""Smoke-test the pddl-validator plugin (Tier 1, no Docker)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = PLUGIN_ROOT / ".venv"
SERVER_DIR = PLUGIN_ROOT / "server"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
NC = "\033[0m"

DOMAIN = """(define (domain bw)
  (:predicates (on ?x ?y) (ontable ?x) (clear ?x) (handempty) (holding ?x))
  (:action pick-up :parameters (?x)
    :precondition (and (clear ?x) (ontable ?x) (handempty))
    :effect (and (holding ?x) (not (ontable ?x)) (not (clear ?x)) (not (handempty))))
  (:action stack :parameters (?x ?y)
    :precondition (and (holding ?x) (clear ?y))
    :effect (and (on ?x ?y) (clear ?x) (handempty) (not (holding ?x)) (not (clear ?y))))
  (:action unstack :parameters (?x ?y)
    :precondition (and (on ?x ?y) (clear ?x) (handempty))
    :effect (and (holding ?x) (clear ?y) (not (on ?x ?y)) (not (clear ?x)) (not (handempty))))
  (:action put-down :parameters (?x)
    :precondition (holding ?x)
    :effect (and (ontable ?x) (clear ?x) (handempty) (not (holding ?x)))))"""

PROBLEM = """(define (problem bw1) (:domain bw)
  (:objects a b)
  (:init (ontable a) (ontable b) (clear a) (clear b) (handempty))
  (:goal (on a b)))"""

VALID_PLAN = """(pick-up a)
(stack a b)"""

INVALID_PLAN = """(stack a b)"""

NUMERIC_DOMAIN = """(define (domain logistics)
  (:requirements :numeric-fluents)
  (:predicates (at ?t ?l) (connected ?l1 ?l2))
  (:functions (fuel ?t))
  (:action drive :parameters (?t ?from ?to)
    :precondition (and (at ?t ?from) (connected ?from ?to) (>= (fuel ?t) 10))
    :effect (and (at ?t ?to) (not (at ?t ?from)) (decrease (fuel ?t) 10))))"""

NUMERIC_PROBLEM = """(define (problem deliver) (:domain logistics)
  (:objects truck loc1 loc2)
  (:init (at truck loc1) (connected loc1 loc2) (= (fuel truck) 20))
  (:goal (at truck loc2)))"""

NUMERIC_PLAN = """(drive truck loc1 loc2)"""

# Typed hierarchy: action parameter declares supertype, plan uses subtype objects.
# Guards against the pyvalidator 0.1.1 bug where subtype compatibility was
# checked with swapped arguments, rejecting every typed IPC benchmark.
TYPED_DOMAIN = """(define (domain transport)
  (:requirements :strips :typing)
  (:types vehicle cargo - object
          truck plane - vehicle)
  (:predicates (parked ?v - vehicle) (stored ?c - cargo))
  (:action start :parameters (?v - vehicle)
    :precondition (parked ?v)
    :effect (not (parked ?v))))"""

TYPED_PROBLEM = """(define (problem transport-p1) (:domain transport)
  (:objects truck1 - truck plane1 - plane box1 - cargo)
  (:init (parked truck1) (parked plane1) (stored box1))
  (:goal (and (not (parked truck1)) (not (parked plane1)))))"""

TYPED_SUBTYPE_PLAN = """(start truck1)
(start plane1)"""

TYPED_SIBLING_PLAN = """(start box1)"""


def ensure_venv() -> Path:
    if not VENV_DIR.is_dir():
        print("Setting up venv...")
        if shutil.which("uv"):
            subprocess.check_call(["uv", "venv", str(VENV_DIR)])
            subprocess.check_call([
                "uv", "pip", "install",
                "--python", str(VENV_DIR / "bin" / "python3"),
                "-r", str(PLUGIN_ROOT / "requirements.txt"),
            ])
        else:
            subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])
            subprocess.check_call([
                str(VENV_DIR / "bin" / "pip"), "install",
                "--quiet", "-r", str(PLUGIN_ROOT / "requirements.txt"),
            ])
    return VENV_DIR / "bin" / "python3"


def run_test_body() -> int:
    sys.path.insert(0, str(SERVER_DIR))
    from validator_server import (
        validate_domain,
        validate_problem,
        validate_plan,
        get_state_transition,
    )

    print(f"Testing pddl-validator plugin")
    print(f"Server: {SERVER_DIR / 'validator_server.py'}")
    print()

    passed = 0
    failed = 0

    def test(name, fn):
        nonlocal passed, failed
        try:
            fn()
            print(f"  OK  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {name}: {e}")
            failed += 1

    def test_imports():
        from validator_server import (  # noqa: F401
            validate_domain,
            validate_problem,
            validate_plan,
            get_state_transition,
        )
    test("Server imports", test_imports)

    def test_syntax_domain_only():
        result = validate_domain(DOMAIN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is True
        assert result["status"] == "VALID"
    test("validate_domain (ok)", test_syntax_domain_only)

    def test_syntax_domain_problem():
        result = validate_problem(DOMAIN, PROBLEM)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is True
    test("validate_problem (ok)", test_syntax_domain_problem)

    def test_valid_plan():
        result = validate_plan(DOMAIN, PROBLEM, VALID_PLAN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is True, f"Expected valid plan, got: {result['status']}"
        assert result["status"] == "VALID"
        assert "VALID" in result["report"]
    test("validate_plan (valid plan)", test_valid_plan)

    def test_invalid_plan():
        result = validate_plan(DOMAIN, PROBLEM, INVALID_PLAN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is False, "Expected invalid plan"
        assert result["status"] == "INVALID"
        assert "details" in result, "Default call should include 'details'"
        assert result["details"]["status"] == "INVALID"
    test("validate_plan (invalid plan)", test_invalid_plan)

    def test_validate_verbose_default_has_details():
        result = validate_plan(DOMAIN, PROBLEM, VALID_PLAN)
        assert set(result.keys()) == {"valid", "status", "report", "details"}, f"Unexpected keys: {result.keys()}"
    test("validate_plan (default verbose=True)", test_validate_verbose_default_has_details)

    def test_validate_verbose_false_drops_details():
        result = validate_plan(DOMAIN, PROBLEM, VALID_PLAN, verbose=False)
        assert set(result.keys()) == {"valid", "status", "report"}, f"Unexpected keys: {result.keys()}"
    test("validate_plan (verbose=False drops details)", test_validate_verbose_false_drops_details)

    def test_invalid_plan_verbose_false_still_diagnosable():
        result = validate_plan(DOMAIN, PROBLEM, INVALID_PLAN, verbose=False)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is False
        assert result["status"] == "INVALID"
        assert result["report"], "report must be non-empty so failures are diagnosable without details"
        assert "details" not in result
    test("validate_plan (invalid plan, verbose=False)", test_invalid_plan_verbose_false_still_diagnosable)

    def test_state_transition_verbose_default_has_report_details():
        result = get_state_transition(DOMAIN, PROBLEM, VALID_PLAN)
        assert set(result.keys()) == {"valid", "report", "steps", "trajectory", "details"}, f"Unexpected keys: {result.keys()}"
    test("get_state_transition (default verbose=True)", test_state_transition_verbose_default_has_report_details)

    def test_state_transition_verbose_false_slim():
        result = get_state_transition(DOMAIN, PROBLEM, VALID_PLAN, verbose=False)
        assert set(result.keys()) == {"valid", "steps", "trajectory"}, f"Unexpected keys: {result.keys()}"
        assert len(result["trajectory"]) >= 1
        assert "boolean_fluents" in result["trajectory"][0]
    test("get_state_transition (verbose=False slim, uncapped)", test_state_transition_verbose_false_slim)

    def test_numeric_validation():
        result = validate_plan(NUMERIC_DOMAIN, NUMERIC_PROBLEM, NUMERIC_PLAN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is True, f"Expected valid numeric plan, got: {result['status']}"
    test("validate_plan (numeric)", test_numeric_validation)

    def test_state_transition():
        result = get_state_transition(DOMAIN, PROBLEM, VALID_PLAN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is True
        assert len(result["steps"]) == 2, f"Expected 2 steps, got {len(result['steps'])}"
        assert result["steps"][0]["action"] == "(pick-up a)"
        assert result["steps"][1]["action"] == "(stack a b)"
        assert len(result["trajectory"]) > 0, "Expected trajectory data"
    test("get_state_transition (blocksworld)", test_state_transition)

    def test_state_transition_numeric():
        result = get_state_transition(NUMERIC_DOMAIN, NUMERIC_PROBLEM, NUMERIC_PLAN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert len(result["steps"]) == 1
        step = result["steps"][0]
        assert step["status"] == "OK"
        assert "numeric" in step.get("changes", {}), f"Expected numeric changes: {step}"
    test("get_state_transition (numeric)", test_state_transition_numeric)

    def test_typed_hierarchy_subtype_accepted():
        result = validate_plan(TYPED_DOMAIN, TYPED_PROBLEM, TYPED_SUBTYPE_PLAN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is True, f"Subtype plan rejected: {result.get('report')}"
    test("validate_plan (typed hierarchy, subtype accepted)", test_typed_hierarchy_subtype_accepted)

    def test_typed_hierarchy_sibling_rejected():
        result = validate_plan(TYPED_DOMAIN, TYPED_PROBLEM, TYPED_SIBLING_PLAN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is False, "Sibling-type plan should have been rejected"
        assert "vehicle" in result["report"] and "box1" in result["report"]
    test("validate_plan (typed hierarchy, sibling rejected)", test_typed_hierarchy_sibling_rejected)

    def test_malformed_pddl():
        result = validate_domain("(define (domain broken))")
        assert "error" not in result or result.get("status") == "SYNTAX_ERROR"
    test("validate_domain (malformed PDDL)", test_malformed_pddl)

    # Regression: pyvalidator's report formatter unconditionally appended
    # "Plan is VALID" when is_valid=True, even on validate_syntax() calls with
    # no plan supplied. The plugin must guarantee the misleading line is absent
    # when no plan was executed — either via the in-plugin strip (workaround,
    # pyvalidator <0.1.5) or via the upstream fix (pyvalidator >=0.1.5).
    def test_no_plan_verdict_leak_domain_only():
        result = validate_domain(DOMAIN, verbose=False)
        assert "error" not in result, result
        assert "Plan is VALID" not in result["report"], \
            f"misleading 'Plan is VALID' leaked into domain-only report: {result['report']!r}"
        assert "Plan is INVALID" not in result["report"]
    test("validate_domain (no plan verdict leak)", test_no_plan_verdict_leak_domain_only)

    def test_no_plan_verdict_leak_domain_problem():
        result = validate_problem(DOMAIN, PROBLEM, verbose=False)
        assert "error" not in result, result
        assert "Plan is VALID" not in result["report"], \
            f"misleading 'Plan is VALID' leaked into domain+problem report: {result['report']!r}"
        assert "Plan is INVALID" not in result["report"]
    test("validate_problem (no plan verdict leak)", test_no_plan_verdict_leak_domain_problem)

    # Edge case: empty plan IS valid when init already satisfies the goal.
    # validate_plan dispatches through validator.validate() (plan-execution
    # mode), so the "Plan is VALID" line is legitimately retained.
    GOAL_MET_PROBLEM = """(define (problem already-solved) (:domain bw)
      (:objects a b)
      (:init (on a b) (clear a) (ontable b) (handempty))
      (:goal (on a b)))"""

    def test_empty_plan_init_satisfies_goal():
        result = validate_plan(DOMAIN, GOAL_MET_PROBLEM, plan=[], verbose=False)
        assert "error" not in result, result
        assert result["valid"] is True, f"empty plan with init satisfying goal should be VALID: {result}"
        assert result["status"] == "VALID"
        assert "Plan is VALID" in result["report"], \
            f"empty plan validating a goal-already-met problem should report 'Plan is VALID': {result['report']!r}"
    test("validate_plan (empty plan, init satisfies goal)", test_empty_plan_init_satisfies_goal)

    # list[str] plan input — should be equivalent to joining and passing as a content string.
    def test_plan_as_list():
        result = validate_plan(DOMAIN, PROBLEM, plan=["(pick-up a)", "(stack a b)"], verbose=False)
        assert "error" not in result, result
        assert result["valid"] is True, f"list-form plan rejected: {result}"
        assert result["status"] == "VALID"
    test("validate_plan (plan as list[str])", test_plan_as_list)

    def test_state_transition_plan_as_list():
        result = get_state_transition(DOMAIN, PROBLEM, plan=["(pick-up a)", "(stack a b)"], verbose=False)
        assert "error" not in result, result
        assert result["valid"] is True
        assert len(result["steps"]) == 2
    test("get_state_transition (plan as list[str])", test_state_transition_plan_as_list)

    # -----------------------------------------------------------------------
    # FastMCP wrapper tests — exercise mcp.call_tool, not the bare functions,
    # so we catch pydantic ValidationError flowing through Tool.run -> ToolError.
    # The bare-function tests above bypass FastMCP entirely.
    # -----------------------------------------------------------------------
    import asyncio
    import json as _json
    from validator_server import mcp
    from mcp.types import CallToolResult

    def _call(tool_name, arguments):
        return asyncio.run(mcp.call_tool(tool_name, arguments))

    def _assert_structured_arg_error(result, *, tool, expected_missing, expected_supplied):
        assert isinstance(result, CallToolResult), f"expected CallToolResult, got {type(result).__name__}"
        assert result.isError is True, f"expected isError=True, got {result.isError}"
        text = result.content[0].text
        payload = _json.loads(text)
        assert payload.get("error") is True, payload
        assert payload.get("errcode") == "missing_required_arg", payload
        assert payload.get("tool") == tool, payload
        for m in expected_missing:
            assert m in payload["missing"], f"{m!r} not in missing: {payload['missing']}"
        for s in expected_supplied:
            assert s in payload["supplied"], f"{s!r} not in supplied: {payload['supplied']}"
        # required is a stable contract — ensure expected missing are listed
        for m in expected_missing:
            assert m in payload["required"], f"{m!r} not in required: {payload['required']}"
        assert isinstance(payload.get("message"), str) and payload["message"], payload

    def test_wrapper_validate_plan_missing_problem_and_plan():
        result = _call("validate_plan", {"domain": DOMAIN, "verbose": False})
        _assert_structured_arg_error(
            result,
            tool="validate_plan",
            expected_missing=["problem", "plan"],
            expected_supplied=["domain", "verbose"],
        )
    test("wrapper: validate_plan missing problem+plan → structured payload", test_wrapper_validate_plan_missing_problem_and_plan)

    def test_wrapper_validate_problem_missing_problem():
        result = _call("validate_problem", {"domain": DOMAIN, "verbose": False})
        _assert_structured_arg_error(
            result,
            tool="validate_problem",
            expected_missing=["problem"],
            expected_supplied=["domain", "verbose"],
        )
    test("wrapper: validate_problem missing problem → structured payload", test_wrapper_validate_problem_missing_problem)

    def test_wrapper_get_state_transition_missing_problem_plan():
        result = _call("get_state_transition", {"domain": DOMAIN, "verbose": False})
        _assert_structured_arg_error(
            result,
            tool="get_state_transition",
            expected_missing=["problem", "plan"],
            expected_supplied=["domain", "verbose"],
        )
    test("wrapper: get_state_transition missing problem+plan → structured payload", test_wrapper_get_state_transition_missing_problem_plan)

    def test_wrapper_validate_domain_missing_domain():
        result = _call("validate_domain", {"verbose": False})
        _assert_structured_arg_error(
            result,
            tool="validate_domain",
            expected_missing=["domain"],
            expected_supplied=["verbose"],
        )
    test("wrapper: validate_domain missing domain → structured payload", test_wrapper_validate_domain_missing_domain)

    def test_wrapper_success_path_unchanged():
        # Sanity: when args are present and valid, wrapper does not intercept —
        # the JSON-serialized success dict reaches the model.
        result = _call("validate_domain", {"domain": DOMAIN, "verbose": False})
        # Success path returns Sequence[ContentBlock] (not CallToolResult) — the
        # lowlevel server normalizes it. Either shape is acceptable as long as
        # the result is not flagged as an error.
        if isinstance(result, CallToolResult):
            assert result.isError is not True, result
    test("wrapper: success path is not intercepted", test_wrapper_success_path_unchanged)

    # -----------------------------------------------------------------------
    # Fix #2: _ensure_plan_file robustness against common LLM serialization shapes.
    # -----------------------------------------------------------------------
    def test_plan_as_list_literal_string():
        # "['(pick-up a)', '(stack a b)']" — Python-list-literal string
        result = validate_plan(DOMAIN, PROBLEM, plan="['(pick-up a)', '(stack a b)']", verbose=False)
        assert "error" not in result, f"list-literal string rejected: {result}"
        assert result["valid"] is True, f"Expected valid plan, got: {result}"
    test("validate_plan (plan as list-literal string)", test_plan_as_list_literal_string)

    def test_plan_as_newline_separated_parens():
        result = validate_plan(DOMAIN, PROBLEM, plan="(pick-up a)\n(stack a b)", verbose=False)
        assert "error" not in result, f"newline-separated rejected: {result}"
        assert result["valid"] is True, f"Expected valid plan, got: {result}"
    test("validate_plan (plan as newline-separated parens)", test_plan_as_newline_separated_parens)

    def test_plan_as_newline_separated_bare_actions_not_rejected_at_shape_gate():
        # The docstring on _ensure_plan_file claims multi-line plan text is
        # accepted "with or without surrounding parens". Without parens
        # pyvalidator likely rejects with a parse error (its concern), but
        # the plugin's shape gate must NOT short-circuit to a FileNotFoundError.
        result = validate_plan(DOMAIN, PROBLEM, plan="pick-up a\nstack a b", verbose=False)
        msg = result.get("message", "")
        assert "does not look like" not in msg, \
            f"multi-line bare-no-parens was rejected at the shape gate: {msg!r}"
    test("validate_plan (multi-line bare actions reach pyvalidator)", test_plan_as_newline_separated_bare_actions_not_rejected_at_shape_gate)

    def test_plan_as_bare_label_clear_error():
        # Single-token bare label (e.g. problem name) is not a usable input —
        # the error message should suggest valid input shapes rather than the
        # generic "PDDL file not found".
        result = validate_plan(DOMAIN, PROBLEM, plan="BW-rand-3", verbose=False)
        assert result.get("error") is True, f"expected error dict, got {result}"
        msg = result["message"].lower()
        assert "bw-rand-3" in msg, msg
        # The new message includes hints — but at minimum it must NOT be a
        # generic "file not found" without context.
        assert "list" in msg or "path" in msg or "label" in msg or "shape" in msg, msg
    test("validate_plan (plan as bare label → clear error)", test_plan_as_bare_label_clear_error)

    # -----------------------------------------------------------------------
    # Fix #4: unknown-fluent precondition lookups return structured PRECONDITION_ERROR
    # rather than bubbling up as a server error.
    # -----------------------------------------------------------------------
    UNKNOWN_FLUENT_DOMAIN = """(define (domain coin)
      (:requirements :numeric-fluents)
      (:predicates (have))
      (:functions (purse))
      (:action buy
        :parameters ()
        :precondition (and (not (have)) (>= (purse) 5))
        :effect (have)))"""

    # Problem deliberately omits (= (purse) X) so the precondition lookup fails
    # — this is the same shape as farmland/zenotravel-numeric b-plans in sweep-5.
    UNKNOWN_FLUENT_PROBLEM = """(define (problem buy-coin) (:domain coin)
      (:init)
      (:goal (have)))"""

    UNKNOWN_FLUENT_PLAN = """(buy)"""

    def test_unknown_fluent_structured_precondition_error():
        result = validate_plan(UNKNOWN_FLUENT_DOMAIN, UNKNOWN_FLUENT_PROBLEM, UNKNOWN_FLUENT_PLAN, verbose=False)
        if result.get("error") is True:
            raise AssertionError(
                f"expected structured verdict, got server error: {result['message']!r}"
            )
        assert result["valid"] is False, result
        # Pin to PRECONDITION_ERROR specifically — if pyvalidator changes and starts
        # returning a native INVALID, this test SHOULD fail loudly so we can delete
        # the in-validator heuristic rather than leave dead code shipping.
        assert result.get("status") == "PRECONDITION_ERROR", result
    test("validate_plan (unknown fluent → structured precondition error)", test_unknown_fluent_structured_precondition_error)

    def test_unknown_fluent_verbose_true_preserves_details_key():
        # The PRECONDITION_ERROR branch must honor the docstring contract that
        # verbose=True returns {valid, status, report, details} — without this,
        # callers (e.g. pddl-fixing skill) hit KeyError on result["details"].
        result = validate_plan(UNKNOWN_FLUENT_DOMAIN, UNKNOWN_FLUENT_PROBLEM, UNKNOWN_FLUENT_PLAN, verbose=True)
        assert result.get("error") is not True, result
        assert result["valid"] is False, result
        assert result.get("status") == "PRECONDITION_ERROR", result
        assert "details" in result, f"verbose=True must include 'details' key: {result.keys()}"
    test("validate_plan (PRECONDITION_ERROR verbose=True keeps details)", test_unknown_fluent_verbose_true_preserves_details_key)

    def test_get_state_transition_unknown_fluent_precondition_error():
        # get_state_transition wraps the same PDDLValidator().validate call as
        # validate_plan and was previously bubbling the unknown-fluent exception
        # as a server error too. Fix #4 must apply symmetrically.
        result = get_state_transition(UNKNOWN_FLUENT_DOMAIN, UNKNOWN_FLUENT_PROBLEM, UNKNOWN_FLUENT_PLAN, verbose=False)
        if result.get("error") is True:
            raise AssertionError(
                f"expected structured verdict, got server error: {result['message']!r}"
            )
        assert result["valid"] is False, result
        assert result.get("status") == "PRECONDITION_ERROR", result
    test("get_state_transition (unknown fluent → structured precondition error)", test_get_state_transition_unknown_fluent_precondition_error)

    def test_get_state_transition_unknown_fluent_verbose_true_keeps_details():
        result = get_state_transition(UNKNOWN_FLUENT_DOMAIN, UNKNOWN_FLUENT_PROBLEM, UNKNOWN_FLUENT_PLAN, verbose=True)
        assert result.get("error") is not True, result
        assert result["valid"] is False, result
        assert result.get("status") == "PRECONDITION_ERROR", result
        assert "details" in result, f"verbose=True must include 'details' key: {result.keys()}"
    test("get_state_transition (PRECONDITION_ERROR verbose=True keeps details)", test_get_state_transition_unknown_fluent_verbose_true_keeps_details)

    def test_plan_as_list_literal_rejects_non_string_items():
        # ast.literal_eval of "[1, 2, 3]" parses to a list — must NOT be silently
        # written as "1\n2\n3" to the plan file (would crash pyvalidator deeper).
        # Behavior: fall through to _ensure_file, which raises FileNotFoundError-as-
        # error-dict with the clearer-shape message.
        result = validate_plan(DOMAIN, PROBLEM, plan="[1, 2, 3]", verbose=False)
        assert result.get("error") is True, f"non-string list elements should error, got: {result}"
    test("validate_plan (plan as list-literal of non-strings → error)", test_plan_as_list_literal_rejects_non_string_items)

    print(f"\n{passed + failed} tests: {passed} passed, {failed} failed")
    if failed:
        print(f"\n{RED}Tests failed.{NC}")
        return 1
    print(f"\n{GREEN}All tests passed.{NC}")
    return 0


def main() -> int:
    if "--in-venv" in sys.argv:
        return run_test_body()
    # Always re-exec into the venv python. Comparing sys.executable to
    # venv_python is unreliable: uv-created venvs symlink to the host python,
    # so the paths look equal under .resolve() even though sys.path / the
    # active site-packages are not the venv's.
    venv_python = ensure_venv()
    os.execv(str(venv_python), [str(venv_python), __file__, "--in-venv"])


if __name__ == "__main__":
    sys.exit(main())
