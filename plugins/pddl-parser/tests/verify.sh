#!/usr/bin/env bash
# verify.sh — Smoke-test the pddl-parser plugin (Tier 1, no Docker).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_ROOT/.venv"

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
FAILURES=0

ERRLOG=$(mktemp)
trap 'rm -f "$ERRLOG"' EXIT

echo "Testing pddl-parser plugin"
echo "Server: $PLUGIN_ROOT/server/parser_server.py"
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

# -- Inline test PDDL (blocksworld) --
read -r -d '' TEST_SCRIPT << 'PYEOF' || true
import sys, os, json
sys.path.insert(0, os.path.join(sys.argv[1], "server"))
from parser_server import get_trajectory

DOMAIN = """(define (domain bw)
  (:requirements :strips)
  (:types block)
  (:predicates (on ?x - block ?y - block) (ontable ?x - block) (clear ?x - block) (handempty) (holding ?x - block))
  (:action pick-up :parameters (?x - block)
    :precondition (and (clear ?x) (ontable ?x) (handempty))
    :effect (and (holding ?x) (not (ontable ?x)) (not (clear ?x)) (not (handempty))))
  (:action stack :parameters (?x - block ?y - block)
    :precondition (and (holding ?x) (clear ?y))
    :effect (and (on ?x ?y) (clear ?x) (handempty) (not (holding ?x)) (not (clear ?y))))
  (:action unstack :parameters (?x - block ?y - block)
    :precondition (and (on ?x ?y) (clear ?x) (handempty))
    :effect (and (holding ?x) (clear ?y) (not (on ?x ?y)) (not (clear ?x)) (not (handempty))))
  (:action put-down :parameters (?x - block)
    :precondition (holding ?x)
    :effect (and (ontable ?x) (clear ?x) (handempty) (not (holding ?x)))))"""

PROBLEM = """(define (problem bw1) (:domain bw)
  (:objects a b - block)
  (:init (ontable a) (ontable b) (clear a) (clear b) (handempty))
  (:goal (and (on a b))))"""

PLAN = "(pick-up a)\n(stack a b)"

# Test 1: Server imports
print("TEST:IMPORT:", end="")
try:
    from parser_server import get_trajectory as gt
    print("OK")
except Exception as e:
    print(f"FAIL:{e}")
    sys.exit(1)

# Test 2: get_trajectory with inline PDDL
print("TEST:TRAJECTORY:", end="")
result = get_trajectory(DOMAIN, PROBLEM, PLAN)
if "error" in result:
    print(f"FAIL:{result['message']}")
    sys.exit(1)

assert "trajectory" in result, f"missing 'trajectory' key: {result}"
assert "final_state" in result, f"missing 'final_state' key: {result}"
assert result["num_steps"] == 2, f"expected 2 steps, got {result['num_steps']}"
assert "1" in result["trajectory"], f"missing step '1': {result['trajectory']}"
assert "2" in result["trajectory"], f"missing step '2': {result['trajectory']}"
assert "state" in result["trajectory"]["1"], f"missing 'state' in step 1"
assert "action" in result["trajectory"]["1"], f"missing 'action' in step 1"
print("OK")

# Test 3: Error handling for invalid input
print("TEST:ERROR_HANDLING:", end="")
bad_result = get_trajectory("(define (domain bad))", PROBLEM, PLAN)
if "error" in bad_result:
    print("OK")
else:
    print(f"FAIL:expected error dict, got {bad_result}")
    sys.exit(1)

print("TEST:DONE")
PYEOF

# Run all tests
echo -n "Server imports...           "
RESULT=$($PYTHON -c "$TEST_SCRIPT" "$PLUGIN_ROOT" 2>"$ERRLOG")
if echo "$RESULT" | grep -q "TEST:IMPORT:OK"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"; FAILURES=$((FAILURES + 1))
    echo "$RESULT" >&2; cat "$ERRLOG" >&2
fi

echo -n "get_trajectory (inline)...  "
if echo "$RESULT" | grep -q "TEST:TRAJECTORY:OK"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"; FAILURES=$((FAILURES + 1))
    echo "$RESULT" >&2; cat "$ERRLOG" >&2
fi

echo -n "Error handling...           "
if echo "$RESULT" | grep -q "TEST:ERROR_HANDLING:OK"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"; FAILURES=$((FAILURES + 1))
    echo "$RESULT" >&2; cat "$ERRLOG" >&2
fi

echo ""
if [ "$FAILURES" -gt 0 ]; then
    echo -e "${RED}${FAILURES} test(s) failed.${NC}"
    exit 1
fi
echo "All tests passed."
