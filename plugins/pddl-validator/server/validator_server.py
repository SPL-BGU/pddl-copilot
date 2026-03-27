"""
pddl_server.py — MCP server wrapping VAL for PDDL validation and state transition simulation.

Calls VAL binary directly via subprocess inside a Docker container.
Accepts inline PDDL content strings (starting with '(') or file paths.
"""

from contextlib import contextmanager
from mcp.server.fastmcp import FastMCP
import os
import shutil
import subprocess
import uuid

mcp = FastMCP("pddl-validator")

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------
VAL_PATH = os.environ.get("PDDL_VAL_PATH", "/opt/planners/VAL")
TEMP_DIR = os.environ.get("PDDL_TEMP_DIR", "/tmp/pddl")
DEFAULT_TIMEOUT = int(os.environ.get("PDDL_TIMEOUT", "120"))

os.makedirs(TEMP_DIR, exist_ok=True)

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


def _run(args: list[str], cwd: str = None, timeout: int = None) -> subprocess.CompletedProcess:
    """Run a subprocess with argument list (no shell). Returns CompletedProcess."""
    return subprocess.run(
        args, cwd=cwd,
        capture_output=True, text=True,
        timeout=timeout or DEFAULT_TIMEOUT,
    )


# ---------------------------------------------------------------------------
# VAL helper
# ---------------------------------------------------------------------------

def _run_val(domain_path: str, problem_path: str = None,
             plan_path: str = None, verbose: bool = True) -> subprocess.CompletedProcess:
    """Run VAL Validate with the given files."""
    args = ["./Validate"]
    if verbose:
        args.append("-v")
    args.extend(["-t", "0.1", domain_path])
    if problem_path:
        args.append(problem_path)
    if plan_path:
        args.append(plan_path)
    return _run(args, cwd=VAL_PATH)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def validate_pddl_syntax(domain: str, problem: str = None, plan: str = None) -> str:
    """
    Validates PDDL syntax and plans using VAL.

    :param domain: File path or PDDL content string for the domain definition.
    :param problem: Optional file path or PDDL content string for the problem.
    :param plan: Optional file path or plan content string for the action sequence.
    :return: Validation output from VAL.
    """
    with _request_dir() as rd:
        try:
            dp = _ensure_file(domain, "domain.pddl", rd)
            pp = _ensure_file(problem, "problem.pddl", rd) if problem else None
            plp = _ensure_file(plan, "plan.solution", rd) if plan else None
        except FileNotFoundError as e:
            return f"error: {e}"

        try:
            r = _run_val(dp, pp, plp)
        except subprocess.TimeoutExpired:
            return f"error: VAL timed out after {DEFAULT_TIMEOUT}s"

        return f"retcode {r.returncode}\n{r.stdout}\n{r.stderr}".strip()


@mcp.tool()
def get_state_transition(domain: str, problem: str, plan: str) -> str:
    """
    Simulates plan execution and returns state transitions using VAL verbose output.

    :param domain: File path or PDDL content string for the domain definition.
    :param problem: File path or PDDL content string for the problem definition.
    :param plan: File path or plan content string for the solution.
    :return: VAL verbose output showing state transitions.
    """
    with _request_dir() as rd:
        try:
            dp = _ensure_file(domain, "domain.pddl", rd)
            pp = _ensure_file(problem, "problem.pddl", rd)
            plp = _ensure_file(plan, "plan.solution", rd)
        except FileNotFoundError as e:
            return f"error: {e}"

        try:
            r = _run_val(dp, pp, plp)
        except subprocess.TimeoutExpired:
            return f"error: VAL timed out after {DEFAULT_TIMEOUT}s"

        return f"{r.stdout}\n{r.stderr}".strip()


if __name__ == "__main__":
    mcp.run(transport="stdio")
