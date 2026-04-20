"""
pddl_server.py — MCP server for PDDL planning via unified-planning engines.

Uses up-fast-downward for classical planning and up-enhsp for numeric planning.
Accepts inline PDDL content strings (starting with '(') or file paths.
"""

from contextlib import contextmanager
from typing import Annotated, Literal
from mcp.server.fastmcp import FastMCP
from pydantic import Field
import os
import shutil
import time
import uuid

from unified_planning.io import PDDLReader
from unified_planning.shortcuts import OneshotPlanner, get_environment
import unified_planning.engines.results as up_results

# Silence the UP factory credits banner — it writes ANSI-coloured text to
# sys.stdout, which corrupts the MCP stdio JSONRPC channel on the client.
get_environment().credits_stream = None

mcp = FastMCP("pddl-solver")

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------
TEMP_DIR = os.environ.get("PDDL_TEMP_DIR", "/tmp/pddl")

_raw_timeout = os.environ.get("PDDL_TIMEOUT", "120")
try:
    DEFAULT_TIMEOUT = int(_raw_timeout)
except ValueError:
    raise ValueError(
        f"PDDL_TIMEOUT must be an integer, got: {_raw_timeout!r}"
    ) from None

_raw_max_log = os.environ.get("PDDL_MAX_LOG_CHARS", "3000")
try:
    MAX_FAILURE_LOG_CHARS = int(_raw_max_log)
except ValueError:
    raise ValueError(
        f"PDDL_MAX_LOG_CHARS must be an integer, got: {_raw_max_log!r}"
    ) from None
DEFAULT_PLANS_DIR = os.path.expanduser("~/plans")

os.makedirs(TEMP_DIR, exist_ok=True)

# Fast Downward search strategy presets (UP parameter format)
# No spaces — UP passes these as CLI args to FD, spaces cause argument splitting
FD_STRATEGIES = {
    "lazy_greedy_cea": "let(hcea,cea(),lazy_greedy([hcea],preferred=[hcea]))",
    "astar_lmcut": "astar(lmcut())",
    "lazy_greedy_ff": "let(hff,ff(),lazy_greedy([hff],preferred=[hff]))",
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


@contextmanager
def _in_dir(path: str):
    """Temporarily chdir into `path`. Fast Downward and ENHSP write intermediate
    files (e.g., `output.sas`) to the current working directory — pin CWD to the
    writable request-scoped temp dir so the solve works even when the server's
    original CWD is read-only."""
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def _ensure_file(content_or_path: str, name: str, req_dir: str) -> str:
    """Write PDDL content to a temp file, or return the existing file path."""
    stripped = content_or_path.strip()

    # Inline PDDL content — write to temp file (may start with ; comments)
    if stripped.startswith("(") or stripped.startswith(";") or "(define " in stripped:
        path = os.path.join(req_dir, name)
        with open(path, "w") as f:
            f.write(content_or_path)
        return path

    # File path — resolve
    if os.path.isfile(stripped):
        return stripped

    # Try expanding ~ and relative paths
    expanded = os.path.expanduser(stripped)
    if os.path.isfile(expanded):
        return expanded

    raise FileNotFoundError(
        f"PDDL file not found: '{stripped}'. "
        f"Pass inline PDDL content or a valid file path."
    )


def _extract_plan(result) -> list[str]:
    """Extract plan actions as lowercase PDDL strings from a UP PlanGenerationResult."""
    if result.plan is None:
        return []
    actions = []
    for ai in result.plan.actions:
        name = ai.action.name
        params = " ".join(str(p) for p in ai.actual_parameters)
        action_str = f"({name} {params})" if params else f"({name})"
        actions.append(action_str.lower())
    return actions


def _solve(engine_name: str, domain: str, problem: str,
           params: dict = None) -> dict:
    """Common solve logic for both planners."""
    with _request_dir() as rd:
        try:
            dp = _ensure_file(domain, "domain.pddl", rd)
            pp = _ensure_file(problem, "problem.pddl", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        try:
            reader = PDDLReader()
            up_problem = reader.parse_problem(dp, pp)
        except Exception as e:
            return {"error": True, "message": f"PDDL parse error: {e}"}

        t1 = time.time()
        try:
            with _in_dir(rd), OneshotPlanner(name=engine_name,
                                             params=params or {}) as planner:
                result = planner.solve(up_problem, timeout=DEFAULT_TIMEOUT)
        except Exception as e:
            return {"error": True, "message": f"Planner error: {e}"}
        t2 = time.time()
        solve_time = round(t2 - t1, 3)

        if result.status in up_results.POSITIVE_OUTCOMES:
            plan = _extract_plan(result)
            return {"plan": plan, "solve_time": solve_time}

        status = result.status
        log = str(result.log_messages) if result.log_messages else ""

        if status in (
            up_results.PlanGenerationResultStatus.UNSOLVABLE_PROVEN,
            up_results.PlanGenerationResultStatus.UNSOLVABLE_INCOMPLETELY,
        ):
            return {"plan": [], "solve_time": solve_time,
                    "note": "Problem is unsolvable"}

        if status == up_results.PlanGenerationResultStatus.TIMEOUT:
            return {"error": True,
                    "message": f"Planner timed out after {DEFAULT_TIMEOUT}s"}

        if status == up_results.PlanGenerationResultStatus.MEMOUT:
            return {"error": True,
                    "message": "Planner ran out of memory"}

        # Planner finished but no plan found
        return {
            "plan": [],
            "solve_time": solve_time,
            "status": str(status),
            "log": log[-MAX_FAILURE_LOG_CHARS:] if log else "",
            "note": "Planner ran but did not find a plan.",
        }


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def classic_planner(
    domain: Annotated[str, Field(description="PDDL content string (e.g., '(define (domain ...) ...)') or absolute file path to a .pddl file.")],
    problem: Annotated[str, Field(description="PDDL content string or absolute file path to a .pddl file for the problem definition.")],
    strategy: Annotated[Literal["lazy_greedy_cea", "astar_lmcut", "lazy_greedy_ff"], Field(description="Search strategy: 'lazy_greedy_cea' (fast, default), 'astar_lmcut' (optimal), 'lazy_greedy_ff' (fast, alternative).")] = "lazy_greedy_cea",
) -> dict:
    """Computes a plan for a classical PDDL planning problem using Fast Downward.
    Does NOT support numeric fluents or durative actions — use numeric_planner for those.
    Returns dict with 'plan' (action list, empty if unsolvable) and 'solve_time' (seconds).
    On failure returns dict with 'error' and 'message'."""
    if strategy not in FD_STRATEGIES:
        return {
            "error": True,
            "message": f"Unknown strategy '{strategy}'. Available: {', '.join(FD_STRATEGIES.keys())}",
        }

    return _solve(
        engine_name="fast-downward",
        domain=domain,
        problem=problem,
        params={"fast_downward_search_config": FD_STRATEGIES[strategy]},
    )


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def numeric_planner(
    domain: Annotated[str, Field(description="PDDL content string (e.g., '(define (domain ...) ...)') or absolute file path to a .pddl file.")],
    problem: Annotated[str, Field(description="PDDL content string or absolute file path to a .pddl file for the problem definition.")],
) -> dict:
    """Computes a plan for a PDDL problem with numeric fluents (:functions, increase, decrease) using ENHSP.
    Use this instead of classic_planner when the domain uses :functions or numeric effects.
    Does NOT support durative/temporal actions.
    Returns dict with 'plan' (action list, empty if unsolvable) and 'solve_time' (seconds).
    On failure returns dict with 'error' and 'message'."""
    return _solve(engine_name="enhsp", domain=domain, problem=problem)


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "openWorldHint": False})
def save_plan(
    plan: Annotated[list, Field(description="List of action strings to save.")],
    domain: Annotated[str, Field(description="Domain path or content (used to derive filename and metadata).")] = None,
    problem: Annotated[str, Field(description="Problem path or content (used to derive filename and metadata).")] = None,
    name: Annotated[str, Field(description="Name for the plan file. Overrides domain/problem-based naming.")] = None,
    output_dir: Annotated[str, Field(description="Directory to save the plan in. Defaults to ~/plans/.")] = None,
    solve_time: Annotated[float, Field(description="Solve time in seconds (included in file metadata header).")] = None,
) -> dict:
    """Saves a computed plan to a file with metadata header.
    Returns dict with 'file_path' (path where plan was saved) and 'plan_length' (number of actions)."""
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
    plans_dir = os.path.expanduser(output_dir.strip()) if output_dir else DEFAULT_PLANS_DIR
    os.makedirs(plans_dir, exist_ok=True)

    # Avoid overwriting existing files
    filepath = os.path.join(plans_dir, f"plan_{tag}.solution")
    if os.path.exists(filepath):
        counter = 1
        while os.path.exists(os.path.join(plans_dir, f"plan_{tag}_{counter}.solution")):
            counter += 1
        filepath = os.path.join(plans_dir, f"plan_{tag}_{counter}.solution")

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

    return {
        "file_path": filepath,
        "plan_length": len(plan),
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
