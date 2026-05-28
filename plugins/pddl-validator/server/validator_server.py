"""
pddl_server.py — MCP server for PDDL validation via pyvalidator.

Uses pyval.PDDLValidator for syntax checking, plan validation, and state simulation.
Accepts inline PDDL content strings (starting with '(') or file paths.
"""

from contextlib import contextmanager
from typing import Annotated, Union
from mcp.server.fastmcp import FastMCP
from pydantic import Field
import os
import shutil
import uuid

from pyval import PDDLValidator

mcp = FastMCP("pddl-validator")

# ---------------------------------------------------------------------------
# Configuration (overridable via environment variables)
# ---------------------------------------------------------------------------
TEMP_DIR = os.environ.get("PDDL_TEMP_DIR", "/tmp/pddl")

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


def _ensure_plan_file(plan_input, name: str, req_dir: str) -> str:
    """Materialize a plan into a file, accepting list[str], str content, or path.
    A list is written verbatim (empty list → empty file, valid when init already
    satisfies the goal)."""
    if isinstance(plan_input, list):
        path = os.path.join(req_dir, name)
        with open(path, "w") as f:
            f.write("\n".join(plan_input))
        return path
    return _ensure_file(plan_input, name, req_dir)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

def _syntax_result_to_dict(result, verbose: bool) -> dict:
    out = {
        "valid": result.is_valid,
        "status": result.status,
        "report": result.report(),
    }
    if verbose:
        out["details"] = result.to_json()
    return out


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def validate_domain(
    domain: Annotated[str, Field(description="PDDL content string (e.g., '(define (domain ...) ...)') or absolute file path to a .pddl file.")],
    verbose: Annotated[bool, Field(description="When True (default), returns the full pyvalidator 'details' dict alongside the summary. Set False to drop 'details' for size-sensitive callers.")] = True,
) -> dict:
    """Validates a PDDL domain's syntax, types, and structural consistency via pyvalidator.
    This is NOT a lexical-only check — it covers type-hierarchy soundness, predicate arity,
    and section nesting in addition to surface syntax. To check that a problem agrees with
    its domain, use validate_problem. To grade a plan, use validate_plan.

    Returns:
        verbose=True:  {"valid": bool, "status": str, "report": str, "details": dict}
        verbose=False: {"valid": bool, "status": str, "report": str}
                       (drops "details" only — "report" is retained)
        Error:         {"error": True, "message": str}

        status is one of: "VALID", "INVALID", "SYNTAX_ERROR", "STRUCTURE_ERROR"."""
    with _request_dir() as rd:
        try:
            dp = _ensure_file(domain, "domain.pddl", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        try:
            result = PDDLValidator().validate_syntax(dp, None)
        except Exception as e:
            return {"error": True, "message": f"Validation error: {e}"}

        return _syntax_result_to_dict(result, verbose)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def validate_problem(
    domain: Annotated[str, Field(description="PDDL content string (e.g., '(define (domain ...) ...)') or absolute file path to a .pddl file.")],
    problem: Annotated[str, Field(description="PDDL content string or absolute file path to a .pddl file for the problem.")],
    verbose: Annotated[bool, Field(description="When True (default), returns the full pyvalidator 'details' dict alongside the summary. Set False to drop 'details' for size-sensitive callers.")] = True,
) -> dict:
    """Validates that a PDDL problem is consistent with its domain via pyvalidator.
    Checks domain syntax, problem syntax, and that the problem's objects, predicates,
    and types resolve against the domain. Does NOT validate a plan — to grade a plan,
    use validate_plan.

    Returns:
        verbose=True:  {"valid": bool, "status": str, "report": str, "details": dict}
        verbose=False: {"valid": bool, "status": str, "report": str}
                       (drops "details" only — "report" is retained)
        Error:         {"error": True, "message": str}

        status is one of: "VALID", "INVALID", "SYNTAX_ERROR", "STRUCTURE_ERROR"."""
    with _request_dir() as rd:
        try:
            dp = _ensure_file(domain, "domain.pddl", rd)
            pp = _ensure_file(problem, "problem.pddl", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        try:
            result = PDDLValidator().validate_syntax(dp, pp)
        except Exception as e:
            return {"error": True, "message": f"Validation error: {e}"}

        return _syntax_result_to_dict(result, verbose)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def validate_plan(
    domain: Annotated[str, Field(description="PDDL content string (e.g., '(define (domain ...) ...)') or absolute file path to a .pddl file.")],
    problem: Annotated[str, Field(description="PDDL content string or absolute file path to a .pddl file for the problem definition.")],
    plan: Annotated[Union[str, list[str]], Field(description="Plan as list of action strings, content string, or absolute file path. An empty list is valid — it represents the empty plan, correct when the initial state already satisfies the goal.")],
    verbose: Annotated[bool, Field(description="When True (default), returns the full pyvalidator 'details' dict alongside the summary. Set False to drop 'details' for size-sensitive callers.")] = True,
) -> dict:
    """Executes a plan against a PDDL (domain, problem) and reports whether it reaches the
    goal via pyvalidator. The "valid" field reflects PLAN CORRECTNESS — preconditions held
    at each step and the goal is satisfied after the final action — not just syntax.

    An empty plan (`[]`) is valid input; it represents the empty plan, which is correct
    when the initial state already satisfies the goal.

    Returns:
        verbose=True:  {"valid": bool, "status": str, "report": str, "details": dict}
        verbose=False: {"valid": bool, "status": str, "report": str}
                       (drops "details" only — "report" is retained. This is asymmetric
                        with get_state_transition, which drops BOTH at verbose=False.)
        Error:         {"error": True, "message": str}

        status is one of: "VALID", "INVALID", "SYNTAX_ERROR", "STRUCTURE_ERROR"."""
    with _request_dir() as rd:
        try:
            dp = _ensure_file(domain, "domain.pddl", rd)
            pp = _ensure_file(problem, "problem.pddl", rd)
            plp = _ensure_plan_file(plan, "plan.solution", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        try:
            result = PDDLValidator().validate(dp, pp, plp)
        except Exception as e:
            return {"error": True, "message": f"Validation error: {e}"}

        return _syntax_result_to_dict(result, verbose)


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def get_state_transition(
    domain: Annotated[str, Field(description="PDDL content string (e.g., '(define (domain ...) ...)') or absolute file path to a .pddl file.")],
    problem: Annotated[str, Field(description="PDDL content string or absolute file path to a .pddl file for the problem definition.")],
    plan: Annotated[Union[str, list[str]], Field(description="Plan as list of action strings, content string, or absolute file path. An empty list simulates the empty plan (initial state = final state).")],
    verbose: Annotated[bool, Field(description="When True (default), returns the verbose pyvalidator 'report' and 'details' fields alongside the structured steps/trajectory. Set False to drop both for size-sensitive callers.")] = True,
) -> dict:
    """Simulates plan execution step-by-step and returns the state after each action,
    with rich precondition-failure diagnostics on bad steps (current values, deficits).
    Use this to debug WHY a plan fails or inspect intermediate states. For a PASS/FAIL
    verdict only, use validate_plan (cheaper, flat shape). For a clean state-action-state
    sequence on a known-valid plan (training data, visualization, backend-agnostic
    extraction), use the parser's `get_trajectory` — leaner output, no diagnostics.

    An empty plan (`[]`) simulates the empty plan (initial state = final state).

    Returns:
        verbose=True:  {"valid": bool, "status": str, "report": str, "steps": list, "trajectory": list, "details": dict}
        verbose=False: {"valid": bool, "status": str, "steps": list, "trajectory": list}
                       (drops BOTH "report" and "details". This is asymmetric with
                        validate_plan, where verbose=False keeps "report".)
        Error:         {"error": True, "message": str}

        status is one of: "VALID", "INVALID", "SYNTAX_ERROR", "STRUCTURE_ERROR". On a
        SYNTAX_ERROR (bad domain/problem) or STRUCTURE_ERROR (undefined action, wrong
        arity) the plan never simulates, so "steps"/"trajectory" are empty — read
        "status" to tell that apart from a plan that executed and failed."""
    with _request_dir() as rd:
        try:
            dp = _ensure_file(domain, "domain.pddl", rd)
            pp = _ensure_file(problem, "problem.pddl", rd)
            plp = _ensure_plan_file(plan, "plan.solution", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        try:
            validator = PDDLValidator()
            result = validator.validate(dp, pp, plp)
        except Exception as e:
            return {"error": True, "message": f"Validation error: {e}"}

        # Build step-by-step output
        steps = []
        for step in result.steps:
            step_data = {
                "index": step.index,
                "action": step.action,
                "status": step.status,
            }
            if step.status == "OK":
                step_data["changes"] = {
                    "boolean": step.boolean_changes,
                    "numeric": {
                        k: {"before": v.before, "after": v.after}
                        for k, v in step.numeric_changes.items()
                    },
                }
            else:
                step_data["unsatisfied_preconditions"] = [
                    {
                        "expression": f.expression,
                        "type": f.type,
                        "current_values": f.current_values,
                        "explanation": f.explanation,
                        **({"deficit": f.deficit} if f.deficit is not None else {}),
                    }
                    for f in step.unsatisfied
                ]
            steps.append(step_data)

        # Build trajectory
        trajectory = []
        for snap in result.trajectory:
            trajectory.append({
                "step": snap.step,
                "action": snap.action,
                "boolean_fluents": snap.boolean_fluents,
                "numeric_fluents": snap.numeric_fluents,
            })

        out = {
            "valid": result.is_valid,
            "status": result.status,
            "steps": steps,
            "trajectory": trajectory,
        }
        if verbose:
            out["report"] = result.report(verbose=True)
            out["details"] = result.to_json()
        return out


if __name__ == "__main__":
    mcp.run(transport="stdio")
