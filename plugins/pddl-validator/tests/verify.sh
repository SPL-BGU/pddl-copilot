#!/usr/bin/env bash
# verify.sh — Smoke-test the pddl-validator plugin against the pddl-sandbox image.
set -euo pipefail
IMAGE="${1:-ghcr.io/spl-bgu/pddl-sandbox:latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVER_SCRIPT="$PLUGIN_ROOT/server/validator_server.py"
GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'

FAILURES=0

ERRLOG=$(mktemp)
trap 'rm -f "$ERRLOG"' EXIT

echo "Testing pddl-validator plugin"
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

cat > /tmp/test/plan.solution <<PLAN
(pick-up a)
(stack a b)
PLAN
'

MOUNT_SERVER="-v ${SERVER_SCRIPT}:/opt/server/pddl_server.py:ro"

# 1. Test server imports
echo -n "Server imports...         "
if docker run --rm $MOUNT_SERVER "$IMAGE" python3 -c "
from pddl_server import validate_pddl_syntax, get_state_transition
print('OK')
" 2>"$ERRLOG" | grep -q "OK"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"; FAILURES=$((FAILURES + 1))
    cat "$ERRLOG" >&2
fi

# 2. VAL via validate_pddl_syntax (retcode=0 means VAL parsed and validated successfully)
echo -n "validate_pddl_syntax...   "
if docker run --rm $MOUNT_SERVER "$IMAGE" bash -c "$SETUP
python3 -c \"
from pddl_server import validate_pddl_syntax
result = validate_pddl_syntax('/tmp/test/domain.pddl', '/tmp/test/problem.pddl')
print('retcode=' + str(result.get('retcode', 'N/A')))
print(result.get('stdout', '')[:200])
\"" 2>"$ERRLOG" | grep -q "retcode=0"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"; FAILURES=$((FAILURES + 1))
    cat "$ERRLOG" >&2
fi

# 3. get_state_transition (VAL outputs "Checking" header and "Plan Repair Advice" section)
echo -n "get_state_transition...   "
if docker run --rm $MOUNT_SERVER "$IMAGE" bash -c "$SETUP
python3 -c \"
from pddl_server import get_state_transition
trace = get_state_transition('/tmp/test/domain.pddl', '/tmp/test/problem.pddl', '/tmp/test/plan.solution')
print(trace.get('stdout', '')[:300])
\"" 2>"$ERRLOG" | grep -Eqi "Checking|Plan Repair"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"; FAILURES=$((FAILURES + 1))
    cat "$ERRLOG" >&2
fi

echo ""
if [ "$FAILURES" -gt 0 ]; then
    echo -e "${RED}${FAILURES} test(s) failed.${NC}"
    exit 1
fi
echo "All tests passed."
