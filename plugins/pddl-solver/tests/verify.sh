#!/usr/bin/env bash
# verify.sh — Smoke-test the pddl-solver plugin against the pddl-sandbox image.
set -euo pipefail
IMAGE="${1:-ghcr.io/spl-bgu/pddl-sandbox:latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVER_SCRIPT="$PLUGIN_ROOT/server/solver_server.py"
GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

echo "Testing pddl-solver plugin"
echo "Image: $IMAGE"
echo "Server: $SERVER_SCRIPT"
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

MOUNT_SERVER="-v ${SERVER_SCRIPT}:/opt/server/pddl_server.py:ro"

# 1. Test server imports
echo -n "Server imports...         "
if docker run --rm $MOUNT_SERVER "$IMAGE" python3 -c "
from pddl_server import classic_planner, numeric_planner, save_plan
print('OK')
" 2>/dev/null | grep -q "OK"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

# 2. Fast Downward via classic_planner
echo -n "classic_planner...        "
if docker run --rm $MOUNT_SERVER "$IMAGE" bash -c "$SETUP
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

# 3. save_plan (metadata + default dir)
echo -n "save_plan...              "
if docker run --rm $MOUNT_SERVER "$IMAGE" bash -c "
python3 -c \"
from pddl_server import save_plan
result = save_plan(['(pick-up a)', '(stack a b)'], name='test', solve_time=0.5)
assert '/plans/plan_test.solution' in result['container_path'], f'Unexpected path: {result}'
with open(result['container_path']) as f:
    content = f.read()
assert '; Plan generated at' in content
assert '; Solve time: 0.5s' in content
assert '; Plan length: 2 actions' in content
assert '(pick-up a)' in content
print('OK')
\"" 2>/dev/null | grep -q "OK"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

# 4. save_plan (anti-overwrite)
echo -n "save_plan anti-overwrite.. "
if docker run --rm $MOUNT_SERVER "$IMAGE" bash -c "
python3 -c \"
from pddl_server import save_plan
r1 = save_plan(['(pick-up a)'], name='dup')
r2 = save_plan(['(stack a b)'], name='dup')
assert r1['container_path'] != r2['container_path'], 'Should not overwrite'
assert '_1.solution' in r2['container_path'], f'Expected counter: {r2}'
print('OK')
\"" 2>/dev/null | grep -q "OK"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

echo ""
echo "Done."
