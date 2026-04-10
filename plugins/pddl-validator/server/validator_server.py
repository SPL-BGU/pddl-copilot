"""
pddl_server.py — MCP server for PDDL validation via pyvalidator.

Uses pyval.PDDLValidator for syntax checking, plan validation, and state simulation.
Accepts inline PDDL content strings (starting with '(') or file paths.
"""

from contextlib import contextmanager
from typing import Annotated
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


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def validate_pddl_syntax(
    domain: Annotated[str, Field(description="PDDL content string (e.g., '(define (domain ...) ...)') or absolute file path to a .pddl file.")],
    problem: Annotated[str, Field(description="PDDL content string or absolute file path to a .pddl file for the problem.")] = None,
    plan: Annotated[str, Field(description="Plan content string or absolute file path for the action sequence to validate.")] = None,
) -> dict:
    """Validates PDDL domains, problems, and plans using pyvalidator.
    Checks syntax when given domain only, checks problem consistency when given domain+problem,
    and verifies plan correctness when given domain+problem+plan.
    Returns:
        {"valid": bool, "status": str, "report": str, "details": dict}
        Error: {"error": True, "message": str}"""
    with _request_dir() as rd:
        try:
            dp = _ensure_file(domain, "domain.pddl", rd)
            pp = _ensure_file(problem, "problem.pddl", rd) if problem else None
            plp = _ensure_file(plan, "plan.solution", rd) if plan else None
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        try:
            validator = PDDLValidator()
            if plp and pp:
                result = validator.validate(dp, pp, plp)
            else:
                result = validator.validate_syntax(dp, pp)
        except Exception as e:
            return {"error": True, "message": f"Validation error: {e}"}

        return {
            "valid": result.is_valid,
            "status": result.status,
            "report": result.report(),
            "details": result.to_json(),
        }


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def get_state_transition(
    domain: Annotated[str, Field(description="PDDL content string (e.g., '(define (domain ...) ...)') or absolute file path to a .pddl file.")],
    problem: Annotated[str, Field(description="PDDL content string or absolute file path to a .pddl file for the problem definition.")],
    plan: Annotated[str, Field(description="Plan content string or absolute file path for the solution to simulate.")],
) -> dict:
    """Simulates plan execution step-by-step and returns the state after each action.
    Use this to debug a plan or inspect intermediate states. For checking plan validity, use validate_pddl_syntax instead.
    Returns:
        {"valid": bool, "report": str, "steps": list, "trajectory": list, "details": dict}
        Error: {"error": True, "message": str}"""
    with _request_dir() as rd:
        try:
            dp = _ensure_file(domain, "domain.pddl", rd)
            pp = _ensure_file(problem, "problem.pddl", rd)
            plp = _ensure_file(plan, "plan.solution", rd)
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

        return {
            "valid": result.is_valid,
            "report": result.report(verbose=True),
            "steps": steps,
            "trajectory": trajectory,
            "details": result.to_json(),
        }


if __name__ == "__main__":
    mcp.run(transport="stdio")
