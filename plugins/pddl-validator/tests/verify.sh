#!/usr/bin/env bash
# verify.sh — Smoke-test the pddl-validator plugin (Tier 1, no Docker).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_ROOT/.venv"

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
FAILURES=0

ERRLOG=$(mktemp)
trap 'rm -f "$ERRLOG"' EXIT

echo "Testing pddl-validator plugin"
echo "Server: $PLUGIN_ROOT/server/validator_server.py"
echo ""

# Ensure venv exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Setting up venv..."
    if command -v uv &>/dev/null; then
        uv venv "$VENV_DIR"
        uv pip install --python "$VENV_DIR/bin/python3" -r "$PLUGIN_ROOT/requirements.txt"
    else
        python3 -m venv "$VENV_DIR"
        "$VENV_DIR/bin/pip" install --quiet -r "$PLUGIN_ROOT/requirements.txt"
    fi
fi

PYTHON="$VENV_DIR/bin/python3"

# -- Test script --
read -r -d '' TEST_SCRIPT << 'PYEOF' || true
import sys, os, json

sys.path.insert(0, os.path.join(sys.argv[1], "server"))
from validator_server import validate_pddl_syntax, get_state_transition

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

passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    try:
        fn()
        print(f"  OK  {name}")
        passed += 1
    except Exception as e:
        print(f"  FAIL {name}: {e}")
        failed += 1

# ---- Tests ----

def test_imports():
    from validator_server import validate_pddl_syntax, get_state_transition
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
    # Should have diagnostic details
    assert "details" in result
    assert result["details"]["status"] == "INVALID"
test("validate_pddl_syntax (invalid plan)", test_invalid_plan)

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
    # Should show numeric change (fuel decreased)
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

# ---- Summary ----
print(f"\n{passed + failed} tests: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
PYEOF

$PYTHON -c "$TEST_SCRIPT" "$PLUGIN_ROOT" 2>"$ERRLOG"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo -e "${RED}Tests failed.${NC}"
    cat "$ERRLOG" >&2
    exit 1
fi

echo ""
echo -e "${GREEN}All tests passed.${NC}"
