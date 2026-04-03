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
from parser_server import (
    get_trajectory, inspect_domain, inspect_problem,
    check_applicable, diff_states, normalize_pddl,
    get_applicable_actions,
)

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

# Test 4: inspect_domain
print("TEST:INSPECT_DOMAIN:", end="")
result = inspect_domain(DOMAIN)
assert "error" not in result, f"inspect_domain error: {result}"
assert result["name"] == "bw", f"expected name 'bw', got {result['name']}"
assert len(result["actions"]) == 4, f"expected 4 actions, got {len(result['actions'])}"
assert len(result["predicates"]) == 5, f"expected 5 predicates, got {len(result['predicates'])}"
assert "block" in result["types"], f"'block' not in types: {result['types']}"
action_names = {a["name"] for a in result["actions"]}
assert action_names == {"pick-up", "stack", "unstack", "put-down"}, f"unexpected actions: {action_names}"
print("OK")

# Test 5: inspect_problem
print("TEST:INSPECT_PROBLEM:", end="")
result = inspect_problem(DOMAIN, PROBLEM)
assert "error" not in result, f"inspect_problem error: {result}"
assert result["name"] == "bw1", f"expected name 'bw1', got {result['name']}"
assert result["num_objects"] == 2, f"expected 2 objects, got {result['num_objects']}"
assert result["num_init_facts"] == 5, f"expected 5 init facts, got {result['num_init_facts']}"
assert result["num_goal_conditions"] == 1, f"expected 1 goal, got {result['num_goal_conditions']}"
assert any("on" in g for g in result["goal"]), f"expected 'on' in goal: {result['goal']}"
print("OK")

# Test 6: check_applicable — applicable action
print("TEST:CHECK_APPLICABLE_YES:", end="")
result = check_applicable(DOMAIN, PROBLEM, "initial", "(pick-up a)")
assert "error" not in result, f"check_applicable error: {result}"
assert result["applicable"] is True, f"expected applicable=True, got {result['applicable']}"
assert len(result["unsatisfied_preconditions"]) == 0, f"expected no unsatisfied, got {result['unsatisfied_preconditions']}"
assert len(result["would_add"]) > 0, f"expected add effects, got {result['would_add']}"
assert len(result["would_delete"]) > 0, f"expected delete effects, got {result['would_delete']}"
print("OK")

# Test 7: check_applicable — inapplicable action
print("TEST:CHECK_APPLICABLE_NO:", end="")
result = check_applicable(DOMAIN, PROBLEM, "initial", "(stack a b)")
assert "error" not in result, f"check_applicable error: {result}"
assert result["applicable"] is False, f"expected applicable=False, got {result['applicable']}"
assert len(result["unsatisfied_preconditions"]) > 0, f"expected unsatisfied preconditions, got {result['unsatisfied_preconditions']}"
print("OK")

# Test 8: diff_states
print("TEST:DIFF_STATES:", end="")
before = json.dumps(["(clear a)", "(clear b)", "(ontable a)", "(ontable b)", "(handempty )"])
after = json.dumps(["(clear b)", "(ontable b)", "(holding a)"])
result = diff_states(before, after)
assert "error" not in result, f"diff_states error: {result}"
assert "(holding a)" in result["added"], f"expected '(holding a)' in added: {result['added']}"
assert "(clear a)" in result["removed"], f"expected '(clear a)' in removed: {result['removed']}"
assert "(clear b)" in result["unchanged"], f"expected '(clear b)' in unchanged: {result['unchanged']}"
print("OK")

# Test 9: normalize_pddl (default output is json)
print("TEST:NORMALIZE_PDDL:", end="")
result = normalize_pddl(DOMAIN)
assert result["valid"] is True, f"expected valid=True, got {result}"
assert result["type"] == "domain", f"expected type='domain', got {result['type']}"
assert result["normalized"] is not None, f"expected normalized content"
assert isinstance(result["normalized"], dict), f"expected dict for json output, got {type(result['normalized'])}"
assert "name" in result["normalized"], f"expected 'name' in normalized json"
# Also test pddl output format
result_pddl = normalize_pddl(DOMAIN, output_format="pddl")
assert result_pddl["valid"] is True
assert "(define" in result_pddl["normalized"], f"expected PDDL content in pddl format"
assert "object - object" not in result_pddl["normalized"], f"implicit 'object' type should not appear in PDDL output: {result_pddl['normalized']}"
print("OK")

# Test 10: normalize_pddl with invalid content
print("TEST:NORMALIZE_PDDL_INVALID:", end="")
result = normalize_pddl("this is not pddl")
assert result["valid"] is False, f"expected valid=False, got {result}"
print("OK")

# Test 11: get_applicable_actions
print("TEST:GET_APPLICABLE_ACTIONS:", end="")
result = get_applicable_actions(DOMAIN, PROBLEM, "initial")
assert "error" not in result, f"get_applicable_actions error: {result}"
assert result["count"] > 0, f"expected some applicable actions, got count={result['count']}"
assert len(result["applicable_actions"]) == result["count"], f"count mismatch"
# In initial state of blocksworld with 2 blocks, pick-up a and pick-up b should be applicable
action_set = set(result["applicable_actions"])
assert "(pick-up a)" in action_set, f"expected '(pick-up a)' in actions: {action_set}"
assert "(pick-up b)" in action_set, f"expected '(pick-up b)' in actions: {action_set}"
print("OK")

# Test 12: check_applicable with state as predicate list
print("TEST:CHECK_APPLICABLE_STATE_LIST:", end="")
state_list = json.dumps(["(holding a)", "(clear b)", "(ontable b)"])
result = check_applicable(DOMAIN, PROBLEM, state_list, "(stack a b)")
assert "error" not in result, f"check_applicable with state list error: {result}"
assert result["applicable"] is True, f"expected applicable=True for stack a b after picking up a"
print("OK")

# Test 13: normalize_pddl with problem (no domain — lightweight parse)
print("TEST:NORMALIZE_PROBLEM_NODOMAIN:", end="")
result = normalize_pddl(PROBLEM)
assert result["valid"] is True, f"expected valid=True, got {result}"
assert result["type"] == "problem", f"expected type='problem', got {result['type']}"
n = result["normalized"]
assert n["name"] == "bw1", f"expected name='bw1', got {n['name']}"
assert n["num_objects"] == 2, f"expected 2 objects, got {n['num_objects']}"
assert n["num_init_facts"] == 5, f"expected 5 init, got {n['num_init_facts']}"
assert n["num_goal_conditions"] == 1, f"expected 1 goal, got {n['num_goal_conditions']}"
assert len(result["warnings"]) > 0, f"expected warning about missing domain"
print("OK")

# Test 14: normalize_pddl with problem + domain (full parse)
print("TEST:NORMALIZE_PROBLEM_DOMAIN:", end="")
result = normalize_pddl(PROBLEM, domain=DOMAIN)
assert result["valid"] is True, f"expected valid=True, got {result}"
assert result["type"] == "problem"
n = result["normalized"]
assert n["num_objects"] == 2
assert n["num_init_facts"] == 5
assert n["num_goal_conditions"] == 1
assert "parser_used" in n, f"expected parser_used in full parse"
print("OK")

# Test 15: inspect_domain with problem (grounded details)
print("TEST:INSPECT_DOMAIN_GROUNDED:", end="")
result = inspect_domain(DOMAIN, problem=PROBLEM)
assert "error" not in result, f"inspect_domain with problem error: {result}"
assert "objects" in result, f"expected 'objects' when problem provided"
assert len(result["objects"]) == 2, f"expected 2 objects, got {len(result['objects'])}"
assert "init" in result, f"expected 'init' when problem provided"
assert "goal" in result, f"expected 'goal' when problem provided"
assert len(result["actions"]) > 0, f"expected actions from domain"
print("OK")

# Test 16: parser_used field present
print("TEST:PARSER_USED:", end="")
result = get_trajectory(DOMAIN, PROBLEM, PLAN)
assert "parser_used" in result, f"missing 'parser_used' key: {result}"
assert result["parser_used"] in ("pddl-plus-parser", "unified-planning"), f"unexpected parser_used: {result['parser_used']}"
result2 = inspect_domain(DOMAIN)
assert "parser_used" in result2, f"missing 'parser_used' in inspect_domain"
result3 = inspect_problem(DOMAIN, PROBLEM)
assert "parser_used" in result3, f"missing 'parser_used' in inspect_problem"
result4 = check_applicable(DOMAIN, PROBLEM, "initial", "(pick-up a)")
assert "parser_used" in result4, f"missing 'parser_used' in check_applicable"
result5 = get_applicable_actions(DOMAIN, PROBLEM, "initial")
assert "parser_used" in result5, f"missing 'parser_used' in get_applicable_actions"
print("OK")

# Test 17: Invalid parser name returns error
print("TEST:INVALID_PARSER:", end="")
result = get_trajectory(DOMAIN, PROBLEM, PLAN, parser="nonexistent")
assert "error" in result, f"expected error for invalid parser, got {result}"
print("OK")

# Test 18+: UP backend (skip if not installed)
try:
    from backend_up import UnifiedPlanningBackend
    UP_AVAILABLE = True
except ImportError:
    UP_AVAILABLE = False

if UP_AVAILABLE:
    print("TEST:UP_TRAJECTORY:", end="")
    result = get_trajectory(DOMAIN, PROBLEM, PLAN, parser="unified-planning")
    assert "error" not in result, f"UP trajectory error: {result}"
    assert result["num_steps"] == 2, f"expected 2 steps, got {result['num_steps']}"
    assert result["parser_used"] == "unified-planning"
    print("OK")

    print("TEST:UP_INSPECT_PROBLEM:", end="")
    result = inspect_problem(DOMAIN, PROBLEM, parser="unified-planning")
    assert "error" not in result, f"UP inspect_problem error: {result}"
    assert result["num_objects"] == 2
    assert result["num_init_facts"] == 5
    assert result["parser_used"] == "unified-planning"
    print("OK")

    print("TEST:UP_CHECK_APPLICABLE:", end="")
    result = check_applicable(DOMAIN, PROBLEM, "initial", "(pick-up a)", parser="unified-planning")
    assert "error" not in result, f"UP check_applicable error: {result}"
    assert result["applicable"] is True
    assert result["parser_used"] == "unified-planning"
    print("OK")

    print("TEST:UP_CHECK_INAPPLICABLE:", end="")
    result = check_applicable(DOMAIN, PROBLEM, "initial", "(stack a b)", parser="unified-planning")
    assert "error" not in result, f"UP check error: {result}"
    assert result["applicable"] is False
    assert len(result["unsatisfied_preconditions"]) > 0
    print("OK")

    print("TEST:UP_APPLICABLE_ACTIONS:", end="")
    result = get_applicable_actions(DOMAIN, PROBLEM, "initial", parser="unified-planning")
    assert "error" not in result, f"UP applicable_actions error: {result}"
    action_set = set(result["applicable_actions"])
    assert "(pick-up a)" in action_set, f"expected '(pick-up a)': {action_set}"
    assert "(pick-up b)" in action_set, f"expected '(pick-up b)': {action_set}"
    assert result["parser_used"] == "unified-planning"
    print("OK")

    # -- New UP parity & coverage tests --

    print("TEST:UP_INSPECT_DOMAIN:", end="")
    result = inspect_domain(DOMAIN, parser="unified-planning")
    assert "error" not in result, f"UP inspect_domain error: {result}"
    assert result["name"] == "bw", f"expected name 'bw', got {result['name']}"
    assert len(result["actions"]) == 4, f"expected 4 actions, got {len(result['actions'])}"
    assert len(result["predicates"]) == 5, f"expected 5 predicates, got {len(result['predicates'])}"
    assert "block" in result["types"], f"'block' not in types: {result['types']}"
    assert ":strips" in result["requirements"], f"expected :strips in requirements: {result['requirements']}"
    print("OK")

    print("TEST:UP_STATE_RECONSTRUCTION:", end="")
    state_preds = json.dumps(["(holding a)", "(clear b)", "(ontable b)"])
    result = check_applicable(DOMAIN, PROBLEM, state_preds, "(stack a b)", parser="unified-planning")
    assert "error" not in result, f"UP state reconstruction error: {result}"
    assert result["applicable"] is True, f"expected applicable for stack a b with custom state"
    assert result["parser_used"] == "unified-planning"
    print("OK")

    print("TEST:UP_PARAM_COUNT_ERROR:", end="")
    result = check_applicable(DOMAIN, PROBLEM, "initial", "(pick-up a b)", parser="unified-planning")
    assert "error" in result, f"expected error for wrong param count: {result}"
    assert "expects" in result["message"] or "parameter" in result["message"].lower(), f"unexpected error: {result['message']}"
    print("OK")

    print("TEST:UP_TYPE_HIERARCHY:", end="")
    DOMAIN_TYPED = """(define (domain typed)
      (:requirements :typing)
      (:types thing - object block - thing)
      (:predicates (on ?x - thing ?y - thing) (clear ?x - block))
      (:action move :parameters (?x - block ?y - block)
        :precondition (and (clear ?x) (clear ?y))
        :effect (and (on ?x ?y) (not (clear ?y)))))"""
    PROBLEM_TYPED = """(define (problem typed1) (:domain typed)
      (:objects a b - block)
      (:init (clear a) (clear b))
      (:goal (on a b)))"""
    result = inspect_domain(DOMAIN_TYPED, parser="unified-planning")
    assert "error" not in result, f"UP typed domain error: {result}"
    assert "block" in result["types"], f"'block' not in types: {result['types']}"
    assert "thing" in result["types"], f"'thing' not in types: {result['types']}"
    result2 = get_applicable_actions(DOMAIN_TYPED, PROBLEM_TYPED, "initial", parser="unified-planning")
    assert "error" not in result2, f"UP typed applicable error: {result2}"
    assert result2["count"] > 0, f"expected applicable actions, got 0"
    print("OK")

    # Parity tests — both backends must produce identical results
    print("TEST:UP_PARITY_CHECK:", end="")
    pp_domain = inspect_domain(DOMAIN, parser="pddl-plus-parser")
    up_domain = inspect_domain(DOMAIN, parser="unified-planning")
    assert pp_domain["name"] == up_domain["name"], f"name mismatch: {pp_domain['name']} vs {up_domain['name']}"
    assert len(pp_domain["actions"]) == len(up_domain["actions"]), f"action count mismatch"
    assert len(pp_domain["predicates"]) == len(up_domain["predicates"]), f"predicate count mismatch"
    pp_action_names = {a["name"] for a in pp_domain["actions"]}
    up_action_names = {a["name"] for a in up_domain["actions"]}
    assert pp_action_names == up_action_names, f"action names differ: {pp_action_names} vs {up_action_names}"
    pp_pred_names = {p["name"] for p in pp_domain["predicates"]}
    up_pred_names = {p["name"] for p in up_domain["predicates"]}
    assert pp_pred_names == up_pred_names, f"predicate names differ: {pp_pred_names} vs {up_pred_names}"
    pp_prob = inspect_problem(DOMAIN, PROBLEM, parser="pddl-plus-parser")
    up_prob = inspect_problem(DOMAIN, PROBLEM, parser="unified-planning")
    assert pp_prob["num_objects"] == up_prob["num_objects"], f"object count: {pp_prob['num_objects']} vs {up_prob['num_objects']}"
    assert pp_prob["init"] == up_prob["init"], f"init mismatch: {pp_prob['init']} vs {up_prob['init']}"
    assert pp_prob["goal"] == up_prob["goal"], f"goal mismatch: {pp_prob['goal']} vs {up_prob['goal']}"
    print("OK")

    print("TEST:NORMALIZE_PARITY:", end="")
    pp_norm = normalize_pddl(DOMAIN, output_format="json")
    # Force UP backend
    up_norm_result = inspect_domain(DOMAIN, parser="unified-planning")
    pp_norm_result = inspect_domain(DOMAIN, parser="pddl-plus-parser")
    # Compare structural equality
    assert pp_norm_result["name"] == up_norm_result["name"]
    pp_types = set(pp_norm_result["types"].keys())
    up_types = set(up_norm_result["types"].keys())
    assert pp_types == up_types, f"types mismatch: {pp_types} vs {up_types}"
    print("OK")

else:
    for name in ["UP_TRAJECTORY", "UP_INSPECT_PROBLEM", "UP_CHECK_APPLICABLE", "UP_CHECK_INAPPLICABLE", "UP_APPLICABLE_ACTIONS",
                  "UP_INSPECT_DOMAIN", "UP_STATE_RECONSTRUCTION", "UP_PARAM_COUNT_ERROR", "UP_TYPE_HIERARCHY",
                  "UP_PARITY_CHECK", "NORMALIZE_PARITY"]:
        print(f"TEST:{name}:SKIP")

print("TEST:DONE")
PYEOF

# Run all tests
RESULT=$($PYTHON -c "$TEST_SCRIPT" "$PLUGIN_ROOT" 2>"$ERRLOG")

# Check each test
for TEST_NAME in IMPORT TRAJECTORY ERROR_HANDLING INSPECT_DOMAIN INSPECT_PROBLEM \
    CHECK_APPLICABLE_YES CHECK_APPLICABLE_NO DIFF_STATES NORMALIZE_PDDL \
    NORMALIZE_PDDL_INVALID GET_APPLICABLE_ACTIONS CHECK_APPLICABLE_STATE_LIST \
    NORMALIZE_PROBLEM_NODOMAIN NORMALIZE_PROBLEM_DOMAIN INSPECT_DOMAIN_GROUNDED \
    PARSER_USED INVALID_PARSER \
    UP_TRAJECTORY UP_INSPECT_PROBLEM UP_CHECK_APPLICABLE UP_CHECK_INAPPLICABLE UP_APPLICABLE_ACTIONS \
    UP_INSPECT_DOMAIN UP_STATE_RECONSTRUCTION UP_PARAM_COUNT_ERROR UP_TYPE_HIERARCHY \
    UP_PARITY_CHECK NORMALIZE_PARITY; do

    LABEL=$(echo "$TEST_NAME" | tr '_' ' ' | tr '[:upper:]' '[:lower:]')
    printf "%-40s" "$LABEL..."
    if echo "$RESULT" | grep -q "TEST:${TEST_NAME}:OK"; then
        echo -e "${GREEN}OK${NC}"
    elif echo "$RESULT" | grep -q "TEST:${TEST_NAME}:SKIP"; then
        echo -e "SKIP"
    else
        echo -e "${RED}FAILED${NC}"; FAILURES=$((FAILURES + 1))
        # Show the specific failure line
        echo "$RESULT" | grep "TEST:${TEST_NAME}:" >&2 || true
    fi
done

# Show any stderr output on failure
if [ "$FAILURES" -gt 0 ]; then
    echo ""
    echo "--- stderr ---"
    cat "$ERRLOG" >&2
fi

echo ""
if [ "$FAILURES" -gt 0 ]; then
    echo -e "${RED}${FAILURES} test(s) failed.${NC}"
    exit 1
fi
echo "All tests passed."
