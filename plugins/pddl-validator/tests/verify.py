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
    from validator_server import validate_pddl_syntax, get_state_transition

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
        from validator_server import validate_pddl_syntax, get_state_transition  # noqa: F401
    test("Server imports", test_imports)

    def test_syntax_domain_only():
        result = validate_pddl_syntax(DOMAIN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is True
        assert result["status"] == "VALID"
    test("validate_pddl_syntax (domain only)", test_syntax_domain_only)

    def test_syntax_domain_problem():
        result = validate_pddl_syntax(DOMAIN, PROBLEM)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is True
    test("validate_pddl_syntax (domain+problem)", test_syntax_domain_problem)

    def test_valid_plan():
        result = validate_pddl_syntax(DOMAIN, PROBLEM, VALID_PLAN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is True, f"Expected valid plan, got: {result['status']}"
        assert result["status"] == "VALID"
        assert "VALID" in result["report"]
    test("validate_pddl_syntax (valid plan)", test_valid_plan)

    def test_invalid_plan():
        result = validate_pddl_syntax(DOMAIN, PROBLEM, INVALID_PLAN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is False, "Expected invalid plan"
        assert result["status"] == "INVALID"
        assert "details" in result, "Default call should include 'details'"
        assert result["details"]["status"] == "INVALID"
    test("validate_pddl_syntax (invalid plan)", test_invalid_plan)

    def test_validate_verbose_default_has_details():
        result = validate_pddl_syntax(DOMAIN, PROBLEM, VALID_PLAN)
        assert set(result.keys()) == {"valid", "status", "report", "details"}, f"Unexpected keys: {result.keys()}"
    test("validate_pddl_syntax (default verbose=True)", test_validate_verbose_default_has_details)

    def test_validate_verbose_false_drops_details():
        result = validate_pddl_syntax(DOMAIN, PROBLEM, VALID_PLAN, verbose=False)
        assert set(result.keys()) == {"valid", "status", "report"}, f"Unexpected keys: {result.keys()}"
    test("validate_pddl_syntax (verbose=False drops details)", test_validate_verbose_false_drops_details)

    def test_invalid_plan_verbose_false_still_diagnosable():
        result = validate_pddl_syntax(DOMAIN, PROBLEM, INVALID_PLAN, verbose=False)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is False
        assert result["status"] == "INVALID"
        assert result["report"], "report must be non-empty so failures are diagnosable without details"
        assert "details" not in result
    test("validate_pddl_syntax (invalid plan, verbose=False)", test_invalid_plan_verbose_false_still_diagnosable)

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
        result = validate_pddl_syntax(NUMERIC_DOMAIN, NUMERIC_PROBLEM, NUMERIC_PLAN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is True, f"Expected valid numeric plan, got: {result['status']}"
    test("validate_pddl_syntax (numeric)", test_numeric_validation)

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
        result = validate_pddl_syntax(TYPED_DOMAIN, TYPED_PROBLEM, TYPED_SUBTYPE_PLAN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is True, f"Subtype plan rejected: {result.get('report')}"
    test("validate_pddl_syntax (typed hierarchy, subtype accepted)", test_typed_hierarchy_subtype_accepted)

    def test_typed_hierarchy_sibling_rejected():
        result = validate_pddl_syntax(TYPED_DOMAIN, TYPED_PROBLEM, TYPED_SIBLING_PLAN)
        assert "error" not in result, f"Error: {result.get('message', result)}"
        assert result["valid"] is False, "Sibling-type plan should have been rejected"
        assert "vehicle" in result["report"] and "box1" in result["report"]
    test("validate_pddl_syntax (typed hierarchy, sibling rejected)", test_typed_hierarchy_sibling_rejected)

    def test_malformed_pddl():
        result = validate_pddl_syntax("(define (domain broken))")
        assert "error" not in result or result.get("status") == "SYNTAX_ERROR"
    test("validate_pddl_syntax (malformed PDDL)", test_malformed_pddl)

    print(f"\n{passed + failed} tests: {passed} passed, {failed} failed")
    if failed:
        print(f"\n{RED}Tests failed.{NC}")
        return 1
    print(f"\n{GREEN}All tests passed.{NC}")
    return 0


def main() -> int:
    if "--in-venv" in sys.argv:
        return run_test_body()
    venv_python = ensure_venv()
    if Path(sys.executable).resolve() != venv_python.resolve():
        os.execv(str(venv_python), [str(venv_python), __file__, "--in-venv"])
    return run_test_body()


if __name__ == "__main__":
    sys.exit(main())
