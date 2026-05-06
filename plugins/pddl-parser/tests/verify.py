#!/usr/bin/env python3
"""Smoke-test the pddl-parser plugin (Tier 1, no Docker)."""
from __future__ import annotations

import json
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

BARE_DOMAIN = """(define (domain bw-bare)
  (:requirements :strips :typing)
  (:types block)
  (:predicates (holding ?x - block) (clear ?x - block)
               (ontable ?x - block) (handempty))
  (:action put-down
    :parameters (?x - block)
    :precondition (holding ?x)
    :effect (and (not (holding ?x)) (clear ?x)
                 (handempty) (ontable ?x))))"""

COUNTERS_DOMAIN = """(define (domain fn-counters)
  (:types counter)
  (:functions (value ?c - counter) (max_int))
  (:action increment
    :parameters (?c - counter)
    :precondition (and (<= (+ (value ?c) 1) (max_int)))
    :effect (and (increase (value ?c) 1))))"""


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
    from parser_server import (
        get_trajectory, inspect_domain, inspect_problem,
        check_applicable, diff_states, normalize_pddl,
        get_applicable_actions,
    )

    print("Testing pddl-parser plugin")
    print(f"Server: {SERVER_DIR / 'parser_server.py'}")
    print()

    passed = 0
    failed = 0
    skipped = 0

    def test(name, fn):
        nonlocal passed, failed
        try:
            fn()
            print(f"  OK   {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {name}: {e}")
            failed += 1

    def skip(name, reason):
        nonlocal skipped
        print(f"  SKIP {name}: {reason}")
        skipped += 1

    # ---- Core tests ----

    def test_imports():
        from parser_server import get_trajectory  # noqa: F401
    test("Server imports", test_imports)

    def test_trajectory():
        result = get_trajectory(DOMAIN, PROBLEM, PLAN)
        assert "error" not in result, f"trajectory error: {result.get('message', result)}"
        assert "trajectory" in result, f"missing 'trajectory' key: {result}"
        assert "final_state" in result, f"missing 'final_state' key: {result}"
        assert result["num_steps"] == 2, f"expected 2 steps, got {result['num_steps']}"
        assert "1" in result["trajectory"], f"missing step '1': {result['trajectory']}"
        assert "2" in result["trajectory"], f"missing step '2': {result['trajectory']}"
        assert "state" in result["trajectory"]["1"], "missing 'state' in step 1"
        assert "action" in result["trajectory"]["1"], "missing 'action' in step 1"
    test("get_trajectory (blocksworld)", test_trajectory)

    def test_error_handling():
        bad_result = get_trajectory("(define (domain bad))", PROBLEM, PLAN)
        assert "error" in bad_result, f"expected error dict, got {bad_result}"
    test("get_trajectory (error handling)", test_error_handling)

    def test_inspect_domain():
        result = inspect_domain(DOMAIN)
        assert "error" not in result, f"inspect_domain error: {result}"
        assert result["name"] == "bw", f"expected name 'bw', got {result['name']}"
        assert len(result["actions"]) == 4, f"expected 4 actions, got {len(result['actions'])}"
        assert len(result["predicates"]) == 5, f"expected 5 predicates, got {len(result['predicates'])}"
        assert "block" in result["types"], f"'block' not in types: {result['types']}"
        action_names = {a["name"] for a in result["actions"]}
        assert action_names == {"pick-up", "stack", "unstack", "put-down"}, f"unexpected actions: {action_names}"
    test("inspect_domain", test_inspect_domain)

    def test_inspect_problem():
        result = inspect_problem(DOMAIN, PROBLEM)
        assert "error" not in result, f"inspect_problem error: {result}"
        assert result["name"] == "bw1", f"expected name 'bw1', got {result['name']}"
        assert result["num_objects"] == 2, f"expected 2 objects, got {result['num_objects']}"
        assert result["num_init_facts"] == 5, f"expected 5 init facts, got {result['num_init_facts']}"
        assert result["num_goal_conditions"] == 1, f"expected 1 goal, got {result['num_goal_conditions']}"
        assert any("on" in g for g in result["goal"]), f"expected 'on' in goal: {result['goal']}"
    test("inspect_problem", test_inspect_problem)

    def test_check_applicable_yes():
        result = check_applicable(DOMAIN, PROBLEM, "initial", "(pick-up a)")
        assert "error" not in result, f"check_applicable error: {result}"
        assert result["applicable"] is True, f"expected applicable=True, got {result['applicable']}"
        assert len(result["unsatisfied_preconditions"]) == 0, f"expected no unsatisfied, got {result['unsatisfied_preconditions']}"
        assert len(result["would_add"]) > 0, f"expected add effects, got {result['would_add']}"
        assert len(result["would_delete"]) > 0, f"expected delete effects, got {result['would_delete']}"
    test("check_applicable (applicable action)", test_check_applicable_yes)

    def test_check_applicable_no():
        result = check_applicable(DOMAIN, PROBLEM, "initial", "(stack a b)")
        assert "error" not in result, f"check_applicable error: {result}"
        assert result["applicable"] is False, f"expected applicable=False, got {result['applicable']}"
        assert len(result["unsatisfied_preconditions"]) > 0, f"expected unsatisfied preconditions, got {result['unsatisfied_preconditions']}"
    test("check_applicable (inapplicable action)", test_check_applicable_no)

    def test_diff_states():
        before = json.dumps(["(clear a)", "(clear b)", "(ontable a)", "(ontable b)", "(handempty )"])
        after = json.dumps(["(clear b)", "(ontable b)", "(holding a)"])
        result = diff_states(before, after)
        assert "error" not in result, f"diff_states error: {result}"
        assert "(holding a)" in result["added"], f"expected '(holding a)' in added: {result['added']}"
        assert "(clear a)" in result["removed"], f"expected '(clear a)' in removed: {result['removed']}"
        assert "(clear b)" in result["unchanged"], f"expected '(clear b)' in unchanged: {result['unchanged']}"
    test("diff_states", test_diff_states)

    def test_normalize_pddl():
        result = normalize_pddl(DOMAIN)
        assert result["valid"] is True, f"expected valid=True, got {result}"
        assert result["type"] == "domain", f"expected type='domain', got {result['type']}"
        assert result["normalized"] is not None, "expected normalized content"
        assert isinstance(result["normalized"], dict), f"expected dict for json output, got {type(result['normalized'])}"
        assert "name" in result["normalized"], "expected 'name' in normalized json"
        result_pddl = normalize_pddl(DOMAIN, output_format="pddl")
        assert result_pddl["valid"] is True
        assert "(define" in result_pddl["normalized"], "expected PDDL content in pddl format"
        assert "object - object" not in result_pddl["normalized"], \
            f"implicit 'object' type should not appear in PDDL output: {result_pddl['normalized']}"
    test("normalize_pddl", test_normalize_pddl)

    def test_normalize_pddl_invalid():
        result = normalize_pddl("this is not pddl")
        assert result["valid"] is False, f"expected valid=False, got {result}"
    test("normalize_pddl (invalid)", test_normalize_pddl_invalid)

    def test_get_applicable_actions():
        result = get_applicable_actions(DOMAIN, PROBLEM, "initial")
        assert "error" not in result, f"get_applicable_actions error: {result}"
        assert result["count"] > 0, f"expected some applicable actions, got count={result['count']}"
        assert len(result["applicable_actions"]) == result["count"], "count mismatch"
        action_set = set(result["applicable_actions"])
        assert "(pick-up a)" in action_set, f"expected '(pick-up a)' in actions: {action_set}"
        assert "(pick-up b)" in action_set, f"expected '(pick-up b)' in actions: {action_set}"
    test("get_applicable_actions", test_get_applicable_actions)

    def test_check_applicable_state_list():
        state_list = json.dumps(["(holding a)", "(clear b)", "(ontable b)"])
        result = check_applicable(DOMAIN, PROBLEM, state_list, "(stack a b)")
        assert "error" not in result, f"check_applicable with state list error: {result}"
        assert result["applicable"] is True, "expected applicable=True for stack a b after picking up a"
    test("check_applicable (state as predicate list)", test_check_applicable_state_list)

    def test_normalize_problem_nodomain():
        result = normalize_pddl(PROBLEM)
        assert result["valid"] is True, f"expected valid=True, got {result}"
        assert result["type"] == "problem", f"expected type='problem', got {result['type']}"
        n = result["normalized"]
        assert n["name"] == "bw1", f"expected name='bw1', got {n['name']}"
        assert n["num_objects"] == 2, f"expected 2 objects, got {n['num_objects']}"
        assert n["num_init_facts"] == 5, f"expected 5 init, got {n['num_init_facts']}"
        assert n["num_goal_conditions"] == 1, f"expected 1 goal, got {n['num_goal_conditions']}"
        assert len(result["warnings"]) > 0, "expected warning about missing domain"
    test("normalize_pddl (problem, no domain)", test_normalize_problem_nodomain)

    def test_normalize_problem_domain():
        result = normalize_pddl(PROBLEM, domain=DOMAIN)
        assert result["valid"] is True, f"expected valid=True, got {result}"
        assert result["type"] == "problem"
        n = result["normalized"]
        assert n["num_objects"] == 2
        assert n["num_init_facts"] == 5
        assert n["num_goal_conditions"] == 1
        assert "parser_used" in n, "expected parser_used in full parse"
    test("normalize_pddl (problem + domain)", test_normalize_problem_domain)

    def test_inspect_domain_grounded():
        result = inspect_domain(DOMAIN, problem=PROBLEM)
        assert "error" not in result, f"inspect_domain with problem error: {result}"
        assert "objects" in result, "expected 'objects' when problem provided"
        assert len(result["objects"]) == 2, f"expected 2 objects, got {len(result['objects'])}"
        assert "init" in result, "expected 'init' when problem provided"
        assert "goal" in result, "expected 'goal' when problem provided"
        assert len(result["actions"]) > 0, "expected actions from domain"
    test("inspect_domain (grounded with problem)", test_inspect_domain_grounded)

    def test_parser_used():
        result = get_trajectory(DOMAIN, PROBLEM, PLAN)
        assert "parser_used" in result, f"missing 'parser_used' key: {result}"
        assert result["parser_used"] in ("pddl-plus-parser", "unified-planning"), f"unexpected parser_used: {result['parser_used']}"
        assert "parser_used" in inspect_domain(DOMAIN), "missing 'parser_used' in inspect_domain"
        assert "parser_used" in inspect_problem(DOMAIN, PROBLEM), "missing 'parser_used' in inspect_problem"
        assert "parser_used" in check_applicable(DOMAIN, PROBLEM, "initial", "(pick-up a)"), "missing 'parser_used' in check_applicable"
        assert "parser_used" in get_applicable_actions(DOMAIN, PROBLEM, "initial"), "missing 'parser_used' in get_applicable_actions"
    test("parser_used field present", test_parser_used)

    def test_invalid_parser():
        result = get_trajectory(DOMAIN, PROBLEM, PLAN, parser="nonexistent")
        assert "error" in result, f"expected error for invalid parser, got {result}"
    test("invalid parser name returns error", test_invalid_parser)

    # ---- UP backend tests (skip if not installed) ----
    try:
        from backend_up import UnifiedPlanningBackend  # noqa: F401
        UP_AVAILABLE = True
    except ImportError:
        UP_AVAILABLE = False

    def test_up_trajectory():
        result = get_trajectory(DOMAIN, PROBLEM, PLAN, parser="unified-planning")
        assert "error" not in result, f"UP trajectory error: {result}"
        assert result["num_steps"] == 2, f"expected 2 steps, got {result['num_steps']}"
        assert result["parser_used"] == "unified-planning"

    def test_up_inspect_problem():
        result = inspect_problem(DOMAIN, PROBLEM, parser="unified-planning")
        assert "error" not in result, f"UP inspect_problem error: {result}"
        assert result["num_objects"] == 2
        assert result["num_init_facts"] == 5
        assert result["parser_used"] == "unified-planning"

    def test_up_check_applicable():
        result = check_applicable(DOMAIN, PROBLEM, "initial", "(pick-up a)", parser="unified-planning")
        assert "error" not in result, f"UP check_applicable error: {result}"
        assert result["applicable"] is True
        assert result["parser_used"] == "unified-planning"

    def test_up_check_inapplicable():
        result = check_applicable(DOMAIN, PROBLEM, "initial", "(stack a b)", parser="unified-planning")
        assert "error" not in result, f"UP check error: {result}"
        assert result["applicable"] is False
        assert len(result["unsatisfied_preconditions"]) > 0

    def test_up_applicable_actions():
        result = get_applicable_actions(DOMAIN, PROBLEM, "initial", parser="unified-planning")
        assert "error" not in result, f"UP applicable_actions error: {result}"
        action_set = set(result["applicable_actions"])
        assert "(pick-up a)" in action_set, f"expected '(pick-up a)': {action_set}"
        assert "(pick-up b)" in action_set, f"expected '(pick-up b)': {action_set}"
        assert result["parser_used"] == "unified-planning"

    def test_up_inspect_domain():
        result = inspect_domain(DOMAIN, parser="unified-planning")
        assert "error" not in result, f"UP inspect_domain error: {result}"
        assert result["name"] == "bw", f"expected name 'bw', got {result['name']}"
        assert len(result["actions"]) == 4, f"expected 4 actions, got {len(result['actions'])}"
        assert len(result["predicates"]) == 5, f"expected 5 predicates, got {len(result['predicates'])}"
        assert "block" in result["types"], f"'block' not in types: {result['types']}"
        assert ":strips" in result["requirements"], f"expected :strips in requirements: {result['requirements']}"

    def test_up_state_reconstruction():
        state_preds = json.dumps(["(holding a)", "(clear b)", "(ontable b)"])
        result = check_applicable(DOMAIN, PROBLEM, state_preds, "(stack a b)", parser="unified-planning")
        assert "error" not in result, f"UP state reconstruction error: {result}"
        assert result["applicable"] is True, "expected applicable for stack a b with custom state"
        assert result["parser_used"] == "unified-planning"

    def test_up_param_count_error():
        result = check_applicable(DOMAIN, PROBLEM, "initial", "(pick-up a b)", parser="unified-planning")
        assert "error" in result, f"expected error for wrong param count: {result}"
        assert "expects" in result["message"] or "parameter" in result["message"].lower(), f"unexpected error: {result['message']}"

    def test_up_type_hierarchy():
        result = inspect_domain(DOMAIN_TYPED, parser="unified-planning")
        assert "error" not in result, f"UP typed domain error: {result}"
        assert "block" in result["types"], f"'block' not in types: {result['types']}"
        assert "thing" in result["types"], f"'thing' not in types: {result['types']}"
        result2 = get_applicable_actions(DOMAIN_TYPED, PROBLEM_TYPED, "initial", parser="unified-planning")
        assert "error" not in result2, f"UP typed applicable error: {result2}"
        assert result2["count"] > 0, "expected applicable actions, got 0"

    def test_up_parity_check():
        pp_domain = inspect_domain(DOMAIN, parser="pddl-plus-parser")
        up_domain = inspect_domain(DOMAIN, parser="unified-planning")
        assert pp_domain["name"] == up_domain["name"], f"name mismatch: {pp_domain['name']} vs {up_domain['name']}"
        assert len(pp_domain["actions"]) == len(up_domain["actions"]), "action count mismatch"
        assert len(pp_domain["predicates"]) == len(up_domain["predicates"]), "predicate count mismatch"
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

    def test_normalize_parity():
        up_norm_result = inspect_domain(DOMAIN, parser="unified-planning")
        pp_norm_result = inspect_domain(DOMAIN, parser="pddl-plus-parser")
        assert pp_norm_result["name"] == up_norm_result["name"]
        pp_types = set(pp_norm_result["types"].keys())
        up_types = set(up_norm_result["types"].keys())
        assert pp_types == up_types, f"types mismatch: {pp_types} vs {up_types}"

    up_tests = [
        ("UP get_trajectory", test_up_trajectory),
        ("UP inspect_problem", test_up_inspect_problem),
        ("UP check_applicable", test_up_check_applicable),
        ("UP check_inapplicable", test_up_check_inapplicable),
        ("UP get_applicable_actions", test_up_applicable_actions),
        ("UP inspect_domain", test_up_inspect_domain),
        ("UP state reconstruction", test_up_state_reconstruction),
        ("UP param count error", test_up_param_count_error),
        ("UP type hierarchy", test_up_type_hierarchy),
        ("UP parity check", test_up_parity_check),
        ("normalize parity", test_normalize_parity),
    ]
    if UP_AVAILABLE:
        for name, fn in up_tests:
            test(name, fn)
    else:
        for name, _ in up_tests:
            skip(name, "unified-planning backend not installed")

    # ---- Flexible action-input tests (exercise both backends) ----
    BACKENDS_TO_TEST = ["unified-planning", "pddl-plus-parser"] if UP_AVAILABLE else ["pddl-plus-parser"]

    def test_flexible_action_sexpr():
        for b in BACKENDS_TO_TEST:
            r = check_applicable(DOMAIN, PROBLEM, "initial", "(pick-up a)", parser=b)
            assert "error" not in r and r["applicable"] is True, f"{b}: {r}"
    test("flexible action input: s-expression", test_flexible_action_sexpr)

    def test_flexible_action_bare():
        for b in BACKENDS_TO_TEST:
            r = check_applicable(DOMAIN, PROBLEM, "initial", "pick-up a", parser=b)
            assert "error" not in r and r["applicable"] is True, f"{b}: {r}"
    test("flexible action input: bare", test_flexible_action_bare)

    def test_flexible_action_func():
        for b in BACKENDS_TO_TEST:
            r = check_applicable(DOMAIN, PROBLEM, "initial", "pick-up(a)", parser=b)
            assert "error" not in r and r["applicable"] is True, f"{b}: {r}"
    test("flexible action input: function-call", test_flexible_action_func)

    def test_flexible_action_case():
        for b in BACKENDS_TO_TEST:
            r = check_applicable(DOMAIN, PROBLEM, "initial", "PICK-UP a", parser=b)
            assert "error" not in r and r["applicable"] is True, f"{b}: {r}"
    test("flexible action input: case-insensitive", test_flexible_action_case)

    def test_flexible_action_comment():
        for b in BACKENDS_TO_TEST:
            r = check_applicable(DOMAIN, PROBLEM, "initial", "(pick-up a) ; from plan", parser=b)
            assert "error" not in r and r["applicable"] is True, f"{b}: {r}"
    test("flexible action input: with comment", test_flexible_action_comment)

    def test_fuzzy_suggestion():
        for b in BACKENDS_TO_TEST:
            r = check_applicable(DOMAIN, PROBLEM, "initial", "pikup a", parser=b)
            assert "error" in r, f"{b}: expected error, got {r}"
            assert "pick-up" in r["message"], f"{b}: expected 'pick-up' in suggestion, got {r['message']}"
    test("fuzzy suggestion on typo", test_fuzzy_suggestion)

    def test_flexible_trajectory_mixed():
        mixed_plan = "(PICK-UP a)\nstack(a, b)"
        for b in BACKENDS_TO_TEST:
            r = get_trajectory(DOMAIN, PROBLEM, mixed_plan, parser=b)
            assert "error" not in r, f"{b}: {r}"
            assert r["num_steps"] == 2, f"{b}: expected 2 steps, got {r['num_steps']}"
    test("get_trajectory mixed action formats", test_flexible_trajectory_mixed)

    # ---- Regression tests for backend-routing + bare-literal workaround ----

    def test_normalize_bare_precondition():
        r = normalize_pddl(BARE_DOMAIN, output_format="pddl")
        assert r["valid"] is True, f"normalize_pddl failed: {r}"
        assert "(holding ?x)" in r["normalized"], \
            f"bare literal lost in default path: {r['normalized']}"
        r2 = inspect_domain(BARE_DOMAIN, parser="pddl-plus-parser")
        put_down = next(a for a in r2["actions"] if a["name"] == "put-down")
        assert "holding" in put_down["precondition"], \
            f"pddl-plus-parser bare literal lost: {put_down['precondition']!r}"
    test("normalize_pddl: bare precondition preserved", test_normalize_bare_precondition)

    def test_normalize_numeric_routing():
        r = normalize_pddl(COUNTERS_DOMAIN, output_format="json")
        assert r["valid"] is True, f"normalize_pddl failed: {r}"
        assert r["normalized"].get("parser_used") == "pddl-plus-parser", \
            f"numeric must route to pddl-plus-parser, got {r['normalized'].get('parser_used')}"
        inc = next(a for a in r["normalized"]["actions"] if a["name"] == "increment")
        assert "(increase" in inc["effect"], \
            f"numeric effect dropped — routing failed: {inc['effect']!r}"
        assert "(<=" in inc["precondition"], \
            f"numeric precondition mangled: {inc['precondition']!r}"
    test("normalize_pddl: numeric routing", test_normalize_numeric_routing)

    def test_numeric_routing_pddl_output():
        r = normalize_pddl(COUNTERS_DOMAIN, output_format="pddl")
        assert r["valid"] is True, f"normalize_pddl failed: {r}"
        assert "(increase" in r["normalized"], \
            f"numeric effect dropped in PDDL output: {r['normalized']}"
        assert "(<=" in r["normalized"], \
            f"numeric precondition dropped in PDDL output: {r['normalized']}"
    test("normalize_pddl: numeric routing PDDL output", test_numeric_routing_pddl_output)

    def test_env_overrides():
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(SERVER_DIR)!r})\n"
            "import parser_server, backends\n"
            "assert parser_server.DEFAULT_MAX_APPLICABLE_ACTIONS == 3, parser_server.DEFAULT_MAX_APPLICABLE_ACTIONS\n"
            "assert backends.MAX_GROUNDING_ATTEMPTS == 42, backends.MAX_GROUNDING_ATTEMPTS\n"
        )
        env = dict(os.environ, PDDL_MAX_APPLICABLE_ACTIONS="3", PDDL_MAX_GROUNDING_ATTEMPTS="42")
        rc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
        assert rc.returncode == 0, f"env-override subprocess failed: {rc.stderr.strip()}"
    test("env-var overrides", test_env_overrides)

    print(f"\n{passed + failed + skipped} tests: {passed} passed, {failed} failed, {skipped} skipped")
    if failed:
        print(f"\n{RED}{failed} test(s) failed.{NC}")
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
