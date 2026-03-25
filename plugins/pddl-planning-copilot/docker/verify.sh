#!/usr/bin/env bash
# verify.sh — Smoke-test the pddl-sandbox image.
set -euo pipefail
IMAGE="${1:-pddl-sandbox}"
GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

echo "Testing image: $IMAGE"
echo ""

# -- Write test PDDL inside the container --
SETUP='
mkdir -p /tmp/test
cat > /tmp/test/domain.pddl <<DOMAIN
(define (domain bw)
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
    :effect (and (ontable ?x) (clear ?x) (handempty) (not (holding ?x)))))
DOMAIN

cat > /tmp/test/problem.pddl <<PROBLEM
(define (problem bw1) (:domain bw)
  (:objects a b)
  (:init (ontable a) (ontable b) (clear a) (clear b) (handempty))
  (:goal (on a b)))
PROBLEM
'

# 1. Test server imports
echo -n "Server imports...         "
if docker run --rm "$IMAGE" python3 -c "
from pddl_server import classic_planner, numeric_planner, validate_pddl_syntax, save_plan, get_state_transition
print('OK')
" 2>/dev/null | grep -q "OK"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

# 2. Fast Downward via classic_planner
echo -n "classic_planner...        "
if docker run --rm "$IMAGE" bash -c "$SETUP
python3 -c \"
from pddl_server import classic_planner
result = classic_planner('/tmp/test/domain.pddl', '/tmp/test/problem.pddl')
plan = result['plan']
t = result['solve_time']
print(f'Plan: {len(plan)} actions in {t:.2f}s')
for a in plan: print(a)
\"" 2>/dev/null | grep -Eqi "pick-up|stack|actions"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

# 3. VAL via validate_pddl_syntax
echo -n "validate_pddl_syntax...   "
if docker run --rm "$IMAGE" bash -c "$SETUP
python3 -c \"
from pddl_server import validate_pddl_syntax
result = validate_pddl_syntax('/tmp/test/domain.pddl', '/tmp/test/problem.pddl')
print(result[:200])
\"" 2>/dev/null | grep -Eqi "retcode|checking"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

# 4. save_plan
echo -n "save_plan...              "
if docker run --rm "$IMAGE" bash -c "
python3 -c \"
from pddl_server import save_plan
result = save_plan(['(pick-up a)', '(stack a b)'], name='test')
print(result['file_path'])
\"" 2>/dev/null | grep -q "plan_test.solution"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

# 5. get_state_transition (end-to-end: solve then simulate)
echo -n "get_state_transition...   "
if docker run --rm "$IMAGE" bash -c "$SETUP
python3 -c \"
from pddl_server import classic_planner, save_plan, get_state_transition
result = classic_planner('/tmp/test/domain.pddl', '/tmp/test/problem.pddl')
plan = result['plan']
sp = save_plan(plan, name='e2e')
trace = get_state_transition('/tmp/test/domain.pddl', '/tmp/test/problem.pddl', sp['file_path'])
print(trace[:300])
\"" 2>/dev/null | grep -Eqi "plan|checking|executing"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

echo ""
echo "Done."
