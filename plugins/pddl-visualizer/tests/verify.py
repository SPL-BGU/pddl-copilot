#!/usr/bin/env python3
"""Smoke-test the pddl-visualizer plugin (Tier 1, no Docker)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = PLUGIN_ROOT / ".venv"
SERVER_DIR = PLUGIN_ROOT / "server"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
NC = "\033[0m"

# Wrapped PDDL state string, as pddl-parser emits.
STATE = "(:init (ontable a) (ontable b) (clear a) (clear b) (handempty))"
# Numeric fluents + an n-ary predicate, to exercise those code paths.
NUMERIC_STATE = (
    "(:state (at truck loc1) (connected loc1 loc2 highway) "
    "(= (fuel truck) 40) (= (total-cost) 7))"
)
# get_trajectory-shaped dict (state before each action + final_state).
TRAJECTORY = {
    "trajectory": {
        "1": {"state": "(:init (ontable a) (ontable b) (clear a) (clear b) (handempty))",
              "action": "(pick-up a)"},
        "2": {"state": "(:state (ontable b) (clear b) (holding a))",
              "action": "(stack a b)"},
    },
    "final_state": "(:state (ontable b) (on a b) (clear a) (handempty))",
    "num_steps": 2,
}


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
    from PIL import Image
    from visualizer_server import (  # noqa: F401
        render_state, render_trajectory,
        extract_predicates, parse_predicate, _union_limits,
    )

    print("Testing pddl-visualizer plugin")
    print(f"Server: {SERVER_DIR / 'visualizer_server.py'}")
    print()

    tmp = tempfile.mkdtemp(prefix="pddlviz-")
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

    def out(name: str) -> str:
        return os.path.join(tmp, name)

    def assert_nonempty_file(path: str):
        assert os.path.isfile(path), f"file not created: {path}"
        assert os.path.getsize(path) > 0, f"file is empty: {path}"

    # ---- parsing unit tests (pure, no rendering) -------------------------
    def test_extract_wrapped():
        preds = extract_predicates(STATE)
        assert preds == ["(ontable a)", "(ontable b)", "(clear a)",
                         "(clear b)", "(handempty)"], preds
    test("extract_predicates (wrapped :init)", test_extract_wrapped)

    def test_extract_json_and_bare():
        assert extract_predicates('["(on a b)", "(clear a)"]') == ["(on a b)", "(clear a)"]
        assert extract_predicates("(on a b) (clear a)") == ["(on a b)", "(clear a)"]
        assert extract_predicates(["(on a b)", "(clear a)"]) == ["(on a b)", "(clear a)"]
        assert extract_predicates("") == []
    test("extract_predicates (json / bare / list / empty)", test_extract_json_and_bare)

    def test_parse_predicate_kinds():
        assert parse_predicate("(handempty)")["kind"] == "flag"
        assert parse_predicate("(clear a)") == {"kind": "unary", "name": "clear", "arg": "a"}
        b = parse_predicate("(on a b)")
        assert (b["kind"], b["a"], b["b"], b["name"]) == ("binary", "a", "b", "on")
        n = parse_predicate("(connected x y z)")
        assert n["kind"] == "nary" and n["args"] == ["x", "y", "z"]
        num = parse_predicate("(= (fuel truck) 40)")
        assert num["kind"] == "numeric" and num["func"] == "fuel"
        assert num["args"] == ["truck"] and num["value"] == "40"
        g = parse_predicate("(= (total-cost) 7)")
        assert g["kind"] == "numeric" and g["args"] == [] and g["value"] == "7"
    test("parse_predicate (flag/unary/binary/nary/numeric)", test_parse_predicate_kinds)

    # ---- render_state ----------------------------------------------------
    def test_render_png():
        r = render_state(STATE, output_path=out("s.png"), title="init")
        assert "error" not in r, r
        assert_nonempty_file(r["image_path"])
        assert r["num_objects"] == 2, r
        assert r["num_predicates"] == 5, r
        assert Image.open(r["image_path"]).format == "PNG"
    test("render_state (blocksworld PNG)", test_render_png)

    def test_render_json_input():
        r = render_state(["(on a b)", "(clear a)", "(ontable b)"], output_path=out("j.png"))
        assert "error" not in r, r
        assert_nonempty_file(r["image_path"])
        assert r["num_objects"] == 2, r
    test("render_state (JSON-array input)", test_render_json_input)

    def test_render_svg():
        r = render_state(STATE, output_path=out("s.svg"), fmt="svg")
        assert "error" not in r, r
        assert_nonempty_file(r["image_path"])
        with open(r["image_path"]) as f:
            assert "<svg" in f.read(2000)
    test("render_state (SVG format)", test_render_svg)

    def test_render_numeric_nary():
        r = render_state(NUMERIC_STATE, output_path=out("num.png"))
        assert "error" not in r, r
        assert_nonempty_file(r["image_path"])
    test("render_state (numeric fluents + n-ary predicate)", test_render_numeric_nary)

    def test_render_long_label_no_clip():
        # Regression: a peripheral node carrying a long multi-property label used
        # to clip at the canvas edge. _fitted_limits must size the axis around the
        # full label. We can't pixel-diff cheaply, but a clipped label would leave
        # content flush against the border; with tight bbox + fitting there is a
        # background-coloured margin on every side. Assert the 1px border is light.
        r = render_state(
            "(:init (on a b) (on b c) (ontable c) (clear a) (handempty) "
            "(heavy a) (red a) (fragile a) (= (weight a) 12))",
            output_path=out("long.png"), title="long label")
        assert "error" not in r, r
        im = Image.open(r["image_path"]).convert("L")
        px = im.load()
        w, h = im.size
        edges = (
            [px[x, 0] for x in range(w)] + [px[x, h - 1] for x in range(w)]
            + [px[0, y] for y in range(h)] + [px[w - 1, y] for y in range(h)]
        )
        # Every border pixel should be near-white (no graph content clipped to it).
        assert min(edges) >= 235, f"content touches the canvas border (min={min(edges)})"
    test("render_state (long peripheral label is not clipped)", test_render_long_label_no_clip)

    def test_union_limits():
        a = ((0.0, 2.0), (0.0, 1.0))
        b = ((-1.0, 1.0), (0.5, 3.0))
        assert _union_limits(a, None) == a
        assert _union_limits(None, b) == b
        assert _union_limits(a, b) == ((-1.0, 2.0), (0.0, 3.0))
    test("_union_limits (shared-window math)", test_union_limits)

    def test_render_empty():
        r = render_state("(:state )", output_path=out("empty.png"))
        assert "error" not in r, r
        assert_nonempty_file(r["image_path"])
        assert r["num_objects"] == 0 and r["num_predicates"] == 0, r
    test("render_state (empty state → placeholder, no crash)", test_render_empty)

    def test_render_layouts():
        for lay in ["spring", "circular", "shell", "kamada_kawai"]:
            r = render_state(STATE, output_path=out(f"l_{lay}.png"), layout=lay)
            assert "error" not in r, (lay, r)
            assert_nonempty_file(r["image_path"])
    test("render_state (all layouts)", test_render_layouts)

    # ---- render_trajectory ----------------------------------------------
    def test_traj_gif():
        r = render_trajectory(TRAJECTORY, output_path=out("t.gif"))
        assert "error" not in r, r
        assert_nonempty_file(r["image_path"])
        assert r["num_frames"] == 3, r  # state1, state2, final_state
        img = Image.open(r["image_path"])
        assert img.format == "GIF", img.format
        assert getattr(img, "n_frames", 1) == 3, getattr(img, "n_frames", 1)
    test("render_trajectory (get_trajectory dict → animated GIF)", test_traj_gif)

    def test_traj_filmstrip():
        r = render_trajectory(TRAJECTORY, output_path=out("t.png"), fmt="filmstrip")
        assert "error" not in r, r
        assert_nonempty_file(r["image_path"])
        assert r["num_frames"] == 3, r
        assert Image.open(r["image_path"]).format == "PNG"
    test("render_trajectory (filmstrip PNG)", test_traj_filmstrip)

    def test_traj_list_input():
        r = render_trajectory(
            ["(ontable a) (clear a)", "(holding a)"],
            output_path=out("tl.gif"),
        )
        assert "error" not in r, r
        assert r["num_frames"] == 2, r
    test("render_trajectory (plain list of states)", test_traj_list_input)

    def test_traj_no_highlight():
        r = render_trajectory(TRAJECTORY, output_path=out("tnh.gif"),
                              highlight_changes=False)
        assert "error" not in r, r
        assert_nonempty_file(r["image_path"])
    test("render_trajectory (highlight_changes=False)", test_traj_no_highlight)

    def test_traj_bad_input():
        r = render_trajectory("not json at all {[", output_path=out("bad.gif"))
        assert r.get("error") is True, r
    test("render_trajectory (malformed input → error dict)", test_traj_bad_input)

    def test_traj_long_no_fig_leak():
        # Regression: a long plan must not hold every frame's figure open at once
        # (matplotlib warns past 20 and it wastes memory). Render ~24 frames and
        # assert no figures leak and the open-figure warning never fires.
        import warnings
        import matplotlib.pyplot as plt
        steps = {str(i): {"state": f"(:state (on o{i} o{i+1}) (clear o{i}))",
                          "action": f"(move o{i} o{i+1})"} for i in range(1, 25)}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            r = render_trajectory({"trajectory": steps}, output_path=out("big.gif"))
        assert "error" not in r, r
        assert r["num_frames"] == 24, r
        assert not plt.get_fignums(), f"leaked figures: {plt.get_fignums()}"
        assert not any("More than 20 figures" in str(x.message) for x in caught), \
            "matplotlib open-figure warning fired (frame figures not closed)"
    test("render_trajectory (long plan: no figure leak / warning)", test_traj_long_no_fig_leak)

    # ---- default output dir + env override ------------------------------
    def test_env_var_render_dir():
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(SERVER_DIR)!r})\n"
            "import visualizer_server as v\n"
            "assert v.DEFAULT_RENDER_DIR.endswith('custom-renders'), v.DEFAULT_RENDER_DIR\n"
        )
        env = dict(os.environ, PDDL_RENDER_DIR=os.path.join(tmp, "custom-renders"))
        rc = subprocess.run([sys.executable, "-c", code], env=env,
                            capture_output=True, text=True)
        assert rc.returncode == 0, f"env-override subprocess failed: {rc.stderr.strip()}"
    test("env-var override (PDDL_RENDER_DIR)", test_env_var_render_dir)

    # ---- FastMCP wrapper: arg validation → structured payload -----------
    import asyncio
    import json as _json
    from visualizer_server import mcp
    from mcp.types import CallToolResult

    def test_wrapper_render_state_missing_state():
        result = asyncio.run(mcp.call_tool("render_state", {"title": "x"}))
        assert isinstance(result, CallToolResult), type(result).__name__
        assert result.isError is True
        payload = _json.loads(result.content[0].text)
        assert payload.get("error") is True, payload
        assert payload.get("errcode") == "missing_required_arg", payload
        assert "state" in payload["missing"], payload
    test("wrapper: render_state missing state → structured payload",
         test_wrapper_render_state_missing_state)

    shutil.rmtree(tmp, ignore_errors=True)

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
    os.execv(str(venv_python), [str(venv_python), __file__, "--in-venv"])


if __name__ == "__main__":
    sys.exit(main())
