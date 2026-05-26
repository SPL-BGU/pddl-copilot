"""
pddl_server.py — MCP server for PDDL planning via unified-planning engines.

Uses up-fast-downward for classical planning and up-enhsp for numeric planning.
Accepts inline PDDL content strings (starting with '(') or file paths.
"""

from contextlib import contextmanager
from typing import Annotated, Literal, Optional
from mcp.server.fastmcp import FastMCP
from pydantic import Field
import glob
import os
import platform
import re
import shutil
import subprocess
import time
import uuid

from unified_planning.io import PDDLReader
from unified_planning.shortcuts import OneshotPlanner, get_environment
import unified_planning.engines.results as up_results


MIN_JAVA_MAJOR = 17


def _parse_java_version_output(blob: str) -> Optional[int]:
    """Extract the major version from `java -version` output. Java writes the
    version to stderr in one of two forms:
      Java 9+:  `openjdk version "17.0.2" 2022-01-18`
      Java ≤8: `java version "1.8.0_321"` — the leading `1.` is stripped here
                so the caller sees 8, not 1.
    Returns None if the blob does not contain a parseable version line.
    """
    m = re.search(r'version\s+"(\d+)(?:\.(\d+))?', blob)
    if not m:
        return None
    major = int(m.group(1))
    if major == 1 and m.group(2):
        return int(m.group(2))
    return major


def _java_major(java_bin: str) -> Optional[int]:
    """Return the major version of `java_bin`, or None if it doesn't run."""
    try:
        r = subprocess.run(
            [java_bin, "-version"], capture_output=True, text=True, timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    return _parse_java_version_output((r.stderr or "") + (r.stdout or ""))


def _discover_java_home() -> Optional[str]:
    """Locate a working JDK >= MIN_JAVA_MAJOR on the host and return its
    JAVA_HOME-style path.

    ENHSP shells out to bare `java`; on macOS the default `/usr/bin/java` is a
    stub that errors unless a JDK is registered under /Library/Java, and
    Homebrew's `openjdk` formula is keg-only (never registered there). Linux
    has analogous gaps when JDK lives under /usr/lib/jvm but no
    update-alternatives link is set. This probe finds those installs so
    end-users do not need to set JAVA_HOME manually.

    Versions < 17 are rejected even if installed — ENHSP requires modern Java,
    and falling through to the existing "no Java" error is more actionable
    than letting ENHSP fail with a JVM-internal stack trace.
    """
    def _eligible(java_bin: str) -> Optional[int]:
        v = _java_major(java_bin)
        return v if v is not None and v >= MIN_JAVA_MAJOR else None

    existing = os.environ.get("JAVA_HOME")
    if existing and _eligible(os.path.join(existing, "bin", "java")) is not None:
        return existing

    system = platform.system()

    if system == "Darwin":
        try:
            r = subprocess.run(
                ["/usr/libexec/java_home", "-v", f"{MIN_JAVA_MAJOR}+"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                path = r.stdout.strip()
                if path and _eligible(os.path.join(path, "bin", "java")) is not None:
                    return path
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        brew_globs = [
            "/opt/homebrew/opt/openjdk*/libexec/openjdk.jdk/Contents/Home",
            "/usr/local/opt/openjdk*/libexec/openjdk.jdk/Contents/Home",
        ]
        brew_candidates: list[tuple[int, str]] = []
        for g in brew_globs:
            for path in glob.glob(g):
                v = _eligible(os.path.join(path, "bin", "java"))
                if v is not None:
                    brew_candidates.append((v, path))
        if brew_candidates:
            return max(brew_candidates, key=lambda x: x[0])[1]

    if system == "Linux":
        linux_candidates: list[tuple[int, str]] = []
        for java_bin in glob.glob("/usr/lib/jvm/*/bin/java"):
            v = _eligible(java_bin)
            if v is not None:
                # JAVA_HOME is two dirs up from bin/java.
                linux_candidates.append(
                    (v, os.path.dirname(os.path.dirname(java_bin)))
                )
        if linux_candidates:
            return max(linux_candidates, key=lambda x: x[0])[1]

    return None


_java_home = _discover_java_home()
if _java_home:
    os.environ["JAVA_HOME"] = _java_home
    os.environ["PATH"] = (
        os.path.join(_java_home, "bin") + os.pathsep + os.environ.get("PATH", "")
    )

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

        # INTERNAL_ERROR / UNSUPPORTED_PROBLEM / INTERMEDIATE — the planner did
        # NOT successfully run-and-conclude-no-plan. Treat as environment error,
        # not as "no plan found" (which would lie via empty plan + misleading note).
        #
        # macOS ships a no-op `java` stub binary that prints exactly the string
        # below when no real JRE is installed — match it for a clean user-facing
        # message. Linux/Windows JVM-missing errors produce different text
        # (e.g., "java: command not found") and fall through to the generic
        # "Planner failed with status X" with the full log attached — still
        # actionable, just not auto-classified.
        trimmed_log = log[-MAX_FAILURE_LOG_CHARS:] if log else ""
        if "Unable to locate a Java Runtime" in log:
            message = (
                "Java runtime not found — required by ENHSP. "
                "Install OpenJDK 17+ (macOS: `brew install openjdk`; "
                "Linux: `apt install openjdk-17-jdk`) and restart the plugin — "
                "it auto-discovers keg-only Homebrew installs and Linux installs "
                "under /usr/lib/jvm with no manual JAVA_HOME needed."
            )
        else:
            message = f"Planner failed with status {status}"
        return {
            "error": True,
            "message": message,
            "status": str(status),
            "solve_time": solve_time,
            "log": trimmed_log,
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
    """Computes a plan for a classical PDDL planning problem using Fast Downward
    (via up-fast-downward). Use this when the domain has no :functions; for domains
    that declare :functions, use numeric_planner instead. Does NOT support
    durative/temporal actions (no planner in this server does). No Java runtime
    required.

    `strategy` selects the Fast Downward search:
      - "lazy_greedy_cea" (default): fast satisficing search via the context-
        enhanced additive heuristic.
      - "astar_lmcut": optimal A* with landmark-cut heuristic. Slower.
      - "lazy_greedy_ff": alternative satisficing search via the FF heuristic.

    Returns:
        Solved:      {"plan": [str, ...], "solve_time": float}
        Unsolvable:  {"plan": [], "solve_time": float,
                      "note": "Problem is unsolvable"}
        Error:       {"error": True, "message": str, ...}
                      Common error causes:
                      - PDDL parse error ("PDDL parse error: ...")
                      - planner timeout ("Planner timed out after Ns")
                      - planner memout ("Planner ran out of memory")
                      - internal/unsupported failure ("Planner failed with
                        status ...", with a truncated `log` field attached)"""
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
    """Computes a plan for a PDDL 2.1 problem with numeric fluents (:functions,
    increase, decrease, numeric preconditions/effects) using ENHSP (via up-enhsp).
    Use this when the domain declares :functions; for purely classical domains,
    classic_planner is faster. Does NOT support durative/temporal actions.

    Requires Java OpenJDK 17+ at runtime. The server auto-discovers JDK installs
    not on PATH (macOS /Library/Java, Homebrew keg-only openjdk under
    /opt/homebrew/opt and /usr/local/opt; Linux /usr/lib/jvm) at startup, so no
    manual JAVA_HOME setup is needed. If no JDK is installed:
      - macOS (system Java stub detected): returns
        {"error": True, "message": "Java runtime not found — required by ENHSP. ..."}
      - Linux/Windows (JVM-launch failures look different across distros):
        returns {"error": True, "message": "Planner failed with status ...",
        "log": "..."} — the truncated `log` carries the actual JVM error.

    Returns:
        Solved:      {"plan": [str, ...], "solve_time": float}
        Unsolvable:  {"plan": [], "solve_time": float,
                      "note": "Problem is unsolvable"}
        Error:       {"error": True, "message": str, ...}
                      Common error causes:
                      - missing Java runtime (see above)
                      - PDDL parse error ("PDDL parse error: ...")
                      - planner timeout / memout
                      - internal/unsupported failure ("Planner failed with
                        status ...", with a truncated `log` field attached)"""
    return _solve(engine_name="enhsp", domain=domain, problem=problem)


@mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": False, "openWorldHint": False})
def save_plan(
    plan: Annotated[list[str], Field(description="List of action strings to save.")],
    domain: Annotated[Optional[str], Field(description="Domain path or content (used to derive filename and metadata).")] = None,
    problem: Annotated[Optional[str], Field(description="Problem path or content (used to derive filename and metadata).")] = None,
    name: Annotated[Optional[str], Field(description="Name fragment for the plan file; becomes <tag> in the auto-generated `plan_<tag>.solution` pattern. Replaces (not augments) the domain/problem-derived tag.")] = None,
    output_dir: Annotated[Optional[str], Field(description="Directory to save the plan in. Defaults to ~/plans/ (auto-created).")] = None,
    solve_time: Annotated[Optional[float], Field(description="Solve time in seconds (included in file metadata header).")] = None,
) -> dict:
    """Saves a computed plan to a file with metadata header.
    Filename pattern is always `plan_<tag>.solution`, where <tag> is `name` if supplied,
    else derived from domain/problem basenames, else a random hex. On collision, a numeric
    suffix is appended (`plan_<tag>_1.solution`, `_2.solution`, ...).
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
