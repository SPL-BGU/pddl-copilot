#!/usr/bin/env bash
# verify.sh — Smoke-test the pddl-solver plugin (Tier 1, no Docker).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_ROOT/.venv"

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
FAILURES=0

ERRLOG=$(mktemp)
trap 'rm -f "$ERRLOG"' EXIT

echo "Testing pddl-solver plugin"
echo "Server: $PLUGIN_ROOT/server/solver_server.py"
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
import sys, os, json, tempfile, shutil

sys.path.insert(0, os.path.join(sys.argv[1], "server"))
from solver_server import classic_planner, numeric_planner, save_plan

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

NUMERIC_DOMAIN = """(define (domain counter)
  (:requirements :numeric-fluents)
  (:functions (count))
  (:action increment
    :parameters ()
    :precondition ()
    :effect (increase (count) 1)))"""

NUMERIC_PROBLEM = """(define (problem count-to-3) (:domain counter)
  (:init (= (count) 0))
  (:goal (>= (count) 3)))"""

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
    from solver_server import classic_planner, numeric_planner, save_plan
test("Server imports", test_imports)

def test_classic():
    result = classic_planner(DOMAIN, PROBLEM)
    assert "error" not in result, f"Error: {result.get('message', result)}"
    assert len(result["plan"]) > 0, "Expected non-empty plan"
    assert result["solve_time"] >= 0
    # Verify plan format: actions should be parenthesized
    for a in result["plan"]:
        assert a.startswith("("), f"Action not in PDDL format: {a}"
test("classic_planner (blocksworld)", test_classic)

def test_classic_strategies():
    for strategy in ["lazy_greedy_cea", "astar_lmcut", "lazy_greedy_ff"]:
        result = classic_planner(DOMAIN, PROBLEM, strategy=strategy)
        assert "error" not in result, f"Strategy {strategy} error: {result.get('message', result)}"
        assert len(result["plan"]) > 0, f"Strategy {strategy}: empty plan"
test("classic_planner (all strategies)", test_classic_strategies)

def test_numeric():
    result = numeric_planner(NUMERIC_DOMAIN, NUMERIC_PROBLEM)
    assert "error" not in result, f"Error: {result.get('message', result)}"
    assert len(result["plan"]) > 0, "Expected non-empty plan"
    assert result["solve_time"] >= 0
test("numeric_planner (counter)", test_numeric)

def test_save():
    tmp = tempfile.mkdtemp()
    try:
        result = save_plan(
            ["(pick-up a)", "(stack a b)"],
            name="test", output_dir=tmp, solve_time=0.5,
        )
        assert os.path.isfile(result["file_path"]), f"File not found: {result['file_path']}"
        assert result["plan_length"] == 2
        with open(result["file_path"]) as f:
            content = f.read()
        assert "; Plan generated at" in content
        assert "; Solve time: 0.5s" in content
        assert "; Plan length: 2 actions" in content
        assert "(pick-up a)" in content
    finally:
        shutil.rmtree(tmp)
test("save_plan (metadata)", test_save)

def test_save_anti_overwrite():
    tmp = tempfile.mkdtemp()
    try:
        r1 = save_plan(["(pick-up a)"], name="dup", output_dir=tmp)
        r2 = save_plan(["(stack a b)"], name="dup", output_dir=tmp)
        assert r1["file_path"] != r2["file_path"], "Should not overwrite"
        assert "_1.solution" in r2["file_path"], f"Expected counter: {r2['file_path']}"
    finally:
        shutil.rmtree(tmp)
test("save_plan (anti-overwrite)", test_save_anti_overwrite)

def test_invalid_strategy():
    result = classic_planner(DOMAIN, PROBLEM, strategy="nonexistent")
    assert result.get("error") is True
test("classic_planner (invalid strategy)", test_invalid_strategy)

def test_bad_pddl():
    result = classic_planner("(define (domain broken))", PROBLEM)
    assert result.get("error") is True
test("classic_planner (malformed PDDL)", test_bad_pddl)

def test_env_var_overrides():
    import subprocess
    server_path = os.path.join(sys.argv[1], "server")
    code = (
        "import sys\n"
        f"sys.path.insert(0, {server_path!r})\n"
        "import solver_server\n"
        "assert solver_server.DEFAULT_TIMEOUT == 999, solver_server.DEFAULT_TIMEOUT\n"
        "assert solver_server.MAX_FAILURE_LOG_CHARS == 500, solver_server.MAX_FAILURE_LOG_CHARS\n"
    )
    env = dict(os.environ, PDDL_TIMEOUT="999", PDDL_MAX_LOG_CHARS="500")
    rc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert rc.returncode == 0, f"env-override subprocess failed: {rc.stderr.strip()}"
test("env-var overrides (PDDL_TIMEOUT, PDDL_MAX_LOG_CHARS)", test_env_var_overrides)

def test_env_var_invalid_raises():
    import subprocess
    server_path = os.path.join(sys.argv[1], "server")
    code = (
        "import sys\n"
        f"sys.path.insert(0, {server_path!r})\n"
        "import solver_server\n"
    )
    env = dict(os.environ, PDDL_TIMEOUT="abc")
    rc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert rc.returncode != 0, "Import should fail on non-integer PDDL_TIMEOUT"
    assert "PDDL_TIMEOUT" in rc.stderr, f"ValueError should name PDDL_TIMEOUT: {rc.stderr.strip()}"
    assert "ValueError" in rc.stderr, f"Expected ValueError, got: {rc.stderr.strip()}"
test("env-var invalid int raises ValueError naming the var", test_env_var_invalid_raises)

def test_classic_planner_no_cwd_pollution():
    # Regression: Fast Downward writes `output.sas` to CWD. The server must pin
    # CWD to its request-scoped temp dir so solves work in read-only envs
    # (e.g., Antigravity container) and do not leave cruft in the caller's CWD.
    stale = os.path.join(os.getcwd(), "output.sas")
    if os.path.exists(stale):
        os.remove(stale)
    result = classic_planner(DOMAIN, PROBLEM)
    assert "error" not in result, result
    assert not os.path.exists(stale), \
        f"classic_planner left output.sas in CWD — solver not chdir'ing into its request dir"
test("classic_planner leaves CWD clean", test_classic_planner_no_cwd_pollution)

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
