"""
pddl_server.py — MCP server wrapping Fast Downward and Metric-FF for PDDL planning.

Calls planner binaries directly via subprocess inside a Docker container.
Accepts inline PDDL content strings (starting with '(') or file paths.
"""

from contextlib import contextmanager
from mcp.server.fastmcp import FastMCP
import glob as globmod
import os
import shutil
import subprocess
import time
import uuid

mcp = FastMCP("pddl-solver")

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------
FD_PATH = os.environ.get("PDDL_FD_PATH", "/opt/planners/FastDownward")
MFF_PATH = os.environ.get("PDDL_MFF_PATH", "/opt/planners/METRIC_FF")
TEMP_DIR = os.environ.get("PDDL_TEMP_DIR", "/tmp/pddl")
DEFAULT_TIMEOUT = int(os.environ.get("PDDL_TIMEOUT", "120"))
DEFAULT_PLANS_DIR = "/workspace/plans"

os.makedirs(TEMP_DIR, exist_ok=True)

# Fast Downward search strategy presets
FD_STRATEGIES = {
    "lazy_greedy_cea": [
        "--evaluator", "hcea=cea()",
        "--search", "lazy_greedy([hcea], preferred=[hcea])",
    ],
    "astar_lmcut": [
        "--search", "astar(lmcut())",
    ],
    "lazy_greedy_ff": [
        "--evaluator", "hff=ff()",
        "--search", "lazy_greedy([hff], preferred=[hff])",
    ],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextmanager
def _request_dir():
    """Create a temp directory for one tool invocation, cleaned up on exit."""
    d = os.path.join(TEMP_DIR, uuid.uuid4().hex[:8])
    os.makedirs(d, exist_ok=True)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _ensure_file(content_or_path: str, name: str, req_dir: str) -> str:
    """Write PDDL content to a temp file, or translate host paths to container paths."""
    stripped = content_or_path.strip()

    # Inline PDDL content — write to temp file (may start with ; comments)
    if stripped.startswith("(") or stripped.startswith(";") or "(define " in stripped:
        path = os.path.join(req_dir, name)
        with open(path, "w") as f:
            f.write(content_or_path)
        return path

    # First, is it already a valid container path? 
    if os.path.isfile(stripped):
        return stripped

    # Translate host absolute path → container path
    host_pwd = os.environ.get("HOST_PWD", "")
    if host_pwd and stripped.startswith(host_pwd):
        translated = "/workspace/" + stripped[len(host_pwd):].lstrip("/")
        if os.path.isfile(translated):
            return translated

    # Relative path — resolve against /workspace
    if not os.path.isabs(stripped):
        workspace_path = os.path.join("/workspace", stripped)
        if os.path.isfile(workspace_path):
            return workspace_path

    raise FileNotFoundError(
        f"PDDL file not found. Path: '{stripped}'. "
        f"Not found at '/workspace/...' either. "
        f"HOST_PWD='{host_pwd}'. "
        f"Ensure the file is inside the mounted directory, or pass inline PDDL content instead."
    )


def _host_to_container(path: str) -> str:
    """Translate a host absolute path to a container path, or return as-is."""
    host_pwd = os.environ.get("HOST_PWD", "")
    if host_pwd and path.startswith(host_pwd):
        return "/workspace/" + path[len(host_pwd):].lstrip("/")
    return path


def _container_to_host(path: str) -> str:
    """Translate a container /workspace path to the host equivalent."""
    host_pwd = os.environ.get("HOST_PWD", "")
    if host_pwd and path.startswith("/workspace"):
        relative = path[len("/workspace"):].lstrip("/")
        return os.path.join(host_pwd, relative) if relative else host_pwd
    return path


def _run(args: list[str], cwd: str = None, timeout: int = None) -> subprocess.CompletedProcess:
    """Run a subprocess with argument list (no shell). Returns CompletedProcess."""
    return subprocess.run(
        args, cwd=cwd,
        capture_output=True, text=True,
        timeout=timeout or DEFAULT_TIMEOUT,
    )


# ---------------------------------------------------------------------------
# Fast Downward helpers
# ---------------------------------------------------------------------------

def _clean_fd_artifacts():
    """Remove Fast Downward temporary files between runs."""
    for name in ("output.sas", "output"):
        p = os.path.join(FD_PATH, name)
        if os.path.isfile(p):
            os.remove(p)
    # Also clean numbered plan files
    for p in globmod.glob(os.path.join(FD_PATH, "sas_plan*")):
        os.remove(p)


def _parse_fd_plan(stdout: str) -> list[str]:
    """Parse Fast Downward plan from sas_plan file(s), falling back to stdout."""
    # FD may write sas_plan, sas_plan.1, sas_plan.2, etc.
    plan_files = sorted(globmod.glob(os.path.join(FD_PATH, "sas_plan*")))
    for plan_file in plan_files:
        plan = []
        with open(plan_file) as f:
            for line in f:
                line = line.strip().rstrip("\r")
                # Strip cost annotations like "; cost = 1"
                if ";" in line:
                    line = line[:line.index(";")].strip()
                if line.startswith("("):
                    plan.append(line.lower())
        if plan:
            return plan

    # Fallback: parse from stdout (some FD versions print plan inline)
    plan = []
    in_plan = False
    for line in stdout.splitlines():
        if "Actual search time" in line:
            in_plan = True
            continue
        if in_plan:
            if "Plan length:" in line:
                break
            stripped = line.strip()
            if ";" in stripped:
                stripped = stripped[:stripped.index(";")].strip()
            if stripped.startswith("("):
                plan.append(stripped.lower())
    return plan


def _parse_mff_plan(stdout: str) -> list[str]:
    """Parse Metric-FF plan from stdout."""
    plan = []
    in_plan = False
    for line in stdout.splitlines():
        if "found legal plan as follows" in line.lower():
            in_plan = True
            continue
        if in_plan:
            stripped = line.strip()
            if not stripped or "plan cost" in stripped.lower() or "time spent" in stripped.lower():
                break
            if ":" in stripped:
                action = stripped.split(":", 1)[1].strip()
                if action:
                    plan.append(f"({action.lower()})")
    return plan


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def classic_planner(domain: str, problem: str, strategy: str = "lazy_greedy_cea") -> dict:
    """
    Computes a plan for a classical PDDL planning problem using Fast Downward.
    Does NOT support numeric fluents or durative actions.

    :param domain: File path or PDDL content string for the domain definition.
    :param problem: File path or PDDL content string for the problem definition.
    :param strategy: Search strategy. Options: "lazy_greedy_cea" (default), "astar_lmcut", "lazy_greedy_ff".
    :return: Dict with 'plan' (action list) and 'solve_time' (seconds).
    """
    if strategy not in FD_STRATEGIES:
        return {
            "error": True,
            "message": f"Unknown strategy '{strategy}'. Available: {', '.join(FD_STRATEGIES.keys())}",
        }

    with _request_dir() as rd:
        try:
            dp = _ensure_file(domain, "domain.pddl", rd)
            pp = _ensure_file(problem, "problem.pddl", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        _clean_fd_artifacts()

        args = ["python3", "fast-downward.py", dp, pp] + FD_STRATEGIES[strategy]
        t1 = time.time()
        try:
            r = _run(args, cwd=FD_PATH)
        except subprocess.TimeoutExpired:
            _clean_fd_artifacts()
            return {"error": True, "message": f"Fast Downward timed out after {DEFAULT_TIMEOUT}s"}
        t2 = time.time()

        combined = r.stdout + r.stderr
        for phrase in ("unsolvable", "goal not fulfilled", "No plan will solve it"):
            if phrase in combined:
                _clean_fd_artifacts()
                return {"plan": [], "solve_time": round(t2 - t1, 3), "note": "Problem is unsolvable"}

        plan = _parse_fd_plan(r.stdout)
        _clean_fd_artifacts()

        if not plan:
            # Include raw output so the agent can diagnose why parsing failed
            return {
                "plan": [],
                "solve_time": round(t2 - t1, 3),
                "exit_code": r.returncode,
                "raw_stdout": r.stdout[-3000:] if r.stdout else "",
                "raw_stderr": r.stderr[-1000:] if r.stderr else "",
                "note": "Planner ran but no plan was parsed. Check raw output for details.",
            }

        return {"plan": plan, "solve_time": round(t2 - t1, 3)}


@mcp.tool()
def numeric_planner(domain: str, problem: str) -> dict:
    """
    Computes a plan for a PDDL 2.1 planning problem with numeric fluents
    using Metric-FF.

    :param domain: File path or PDDL content string for the domain definition.
    :param problem: File path or PDDL content string for the problem definition.
    :return: Dict with 'plan' (action list) and 'solve_time' (seconds).
    """
    with _request_dir() as rd:
        try:
            dp = _ensure_file(domain, "domain.pddl", rd)
            pp = _ensure_file(problem, "problem.pddl", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        args = ["./ff", "-o", dp, "-f", pp, "-s", "0"]
        t1 = time.time()
        try:
            r = _run(args, cwd=MFF_PATH)
        except subprocess.TimeoutExpired:
            return {"error": True, "message": f"Metric-FF timed out after {DEFAULT_TIMEOUT}s"}
        t2 = time.time()

        combined = r.stdout + r.stderr
        for phrase in ("unsolvable", "goal not fulfilled", "No plan will solve it"):
            if phrase in combined:
                return {"plan": [], "solve_time": round(t2 - t1, 3), "note": "Problem is unsolvable"}

        plan = _parse_mff_plan(r.stdout)

        if not plan:
            return {
                "plan": [],
                "solve_time": round(t2 - t1, 3),
                "exit_code": r.returncode,
                "raw_stdout": r.stdout[-3000:] if r.stdout else "",
                "raw_stderr": r.stderr[-1000:] if r.stderr else "",
                "note": "Planner ran but no plan was parsed. Check raw output for details.",
            }

        return {"plan": plan, "solve_time": round(t2 - t1, 3)}


@mcp.tool()
def save_plan(
    plan: list,
    domain: str = None,
    problem: str = None,
    name: str = None,
    output_dir: str = None,
    solve_time: float = None,
) -> dict:
    """
    Saves a computed plan to a file with metadata header.

    :param plan: List of action strings to save.
    :param domain: Optional domain path or content (used to derive filename and metadata).
    :param problem: Optional problem path or content (used to derive filename and metadata).
    :param name: Optional name for the plan file. Overrides domain/problem-based naming.
    :param output_dir: Optional directory to save the plan in. Accepts host paths. Defaults to ~/plans/.
    :param solve_time: Optional solve time in seconds (included in file metadata header).
    :return: Dict with 'file_path' (host path), 'container_path', and 'plan_length'.
    """
    # Tag derivation
    if name:
        tag = name
    else:
        parts = []
        if domain and not domain.strip().startswith("(") and not domain.strip().startswith(";"):
            dom_name = os.path.splitext(os.path.basename(domain.strip()))[0]
            if dom_name.lower() != "domain":
                parts.append(dom_name)
        if problem and not problem.strip().startswith("(") and not problem.strip().startswith(";"):
            prob_name = os.path.splitext(os.path.basename(problem.strip()))[0]
            if prob_name.lower() != "problem":
                parts.append(prob_name)
        tag = "_".join(parts) if parts else uuid.uuid4().hex[:6]

    # Resolve output directory
    if output_dir:
        container_dir = _host_to_container(output_dir.strip())
    else:
        container_dir = DEFAULT_PLANS_DIR
    os.makedirs(container_dir, exist_ok=True)

    # Avoid overwriting existing files
    filepath = os.path.join(container_dir, f"plan_{tag}.solution")
    if os.path.exists(filepath):
        counter = 1
        while os.path.exists(os.path.join(container_dir, f"plan_{tag}_{counter}.solution")):
            counter += 1
        filepath = os.path.join(container_dir, f"plan_{tag}_{counter}.solution")

    # Write file with metadata header
    with open(filepath, "w") as f:
        f.write(f"; Plan generated at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        if domain and not domain.strip().startswith("(") and not domain.strip().startswith(";"):
            f.write(f"; Domain: {os.path.basename(domain.strip())}\n")
        if problem and not problem.strip().startswith("(") and not problem.strip().startswith(";"):
            f.write(f"; Problem: {os.path.basename(problem.strip())}\n")
        if solve_time is not None:
            f.write(f"; Solve time: {solve_time}s\n")
        f.write(f"; Plan length: {len(plan)} actions\n")
        f.write("\n")
        for action in plan:
            f.write(str(action) + "\n")

    host_path = _container_to_host(filepath)
    return {
        "file_path": host_path,
        "container_path": filepath,
        "plan_length": len(plan),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
