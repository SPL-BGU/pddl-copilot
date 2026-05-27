"""
pddl_server.py — MCP server for PDDL validation via pyvalidator.

Uses pyval.PDDLValidator for syntax checking, plan validation, and state simulation.
Accepts inline PDDL content strings (starting with '(') or file paths.
"""

from contextlib import contextmanager
from typing import Annotated, Union
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import CallToolResult, TextContent
from pydantic import Field, ValidationError
import ast
import json
import os
import shutil
import uuid

from pyval import PDDLValidator


# NOTE: this class is duplicated verbatim in pddl-solver and pddl-parser. The
# marketplace plugin-isolation rule (.claude/rules/marketplace.md) forbids
# cross-plugin imports; each plugin must be installable standalone. Don't try
# to "DRY" this into a shared module — it would break isolation. Fix it in
# all three places when changing the payload contract.
class _StructuredArgErrorFastMCP(FastMCP):
    """FastMCP subclass that converts pydantic arg-validation errors into a
    one-line structured payload so small models can parse and recover.

    FastMCP wraps every tool exception in ToolError("Error executing tool ...");
    when the inner cause is a pydantic ValidationError we emit a fixed 7-key
    payload (error/errcode/tool/missing/required/supplied/message) as
    isError=True content. Non-ValidationError ToolErrors are re-raised so the
    existing lowlevel error path is unchanged."""

    async def call_tool(self, name, arguments, *args, **kwargs):
        try:
            return await super().call_tool(name, arguments, *args, **kwargs)
        except ToolError as e:
            cause = getattr(e, "__cause__", None)
            if not isinstance(cause, ValidationError):
                raise
            tool = self._tool_manager.get_tool(name)
            if tool is None:
                raise
            required = [
                (fi.alias or fname)
                for fname, fi in tool.fn_metadata.arg_model.model_fields.items()
                if fi.is_required()
            ]
            supplied = list((arguments or {}).keys())
            errs = cause.errors()
            missing = [
                str(err["loc"][0])
                for err in errs
                if err.get("type") == "missing" and err.get("loc")
            ]
            if missing:
                errcode = "missing_required_arg"
                message = (
                    f"{name}: missing required argument {missing[0]!r}. "
                    f"Required args: {', '.join(required)}."
                )
            else:
                errcode = "arg_validation_failed"
                first = errs[0] if errs else {"msg": "invalid", "loc": ("?",)}
                bad_loc = first.get("loc") or ("?",)
                bad_arg = str(bad_loc[0])
                message = f"{name}: argument {bad_arg!r}: {first.get('msg', 'invalid')}."
            payload = {
                "error": True,
                "errcode": errcode,
                "tool": name,
                "missing": missing,
                "required": required,
                "supplied": supplied,
                "message": message,
            }
            return CallToolResult(
                isError=True,
                content=[TextContent(type="text", text=json.dumps(payload))],
            )


mcp = _StructuredArgErrorFastMCP("pddl-validator")

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
        f"PDDL argument {stripped!r} does not look like PDDL content or a file path. "
        f"PDDL content must start with '(' (e.g. '(define (domain ...) ...)') or be "
        f"a valid file path. A bare problem name or label is not a usable input."
    )


def _ensure_plan_file(plan_input, name: str, req_dir: str) -> str:
    """Materialize a plan into a file, accepting list[str], str content, or path.
    A list is written verbatim (empty list → empty file, valid when init already
    satisfies the goal).

    Robust to common LLM serialization shapes also handled here:
    - Python-list-literal string ("['(pick-up a)', '(stack a b)']") → parsed and
      written as a list.
    - Multi-line action text (with or without surrounding parens, e.g. lines like
      "(pick-up a)" or "pick-up a") → written verbatim; pyvalidator parses it.

    Single-token bare labels (e.g. "BW-rand-3") still fall through to the
    file-path resolver and ultimately to `_ensure_file`'s FileNotFoundError,
    which now suggests valid input shapes.
    """
    if isinstance(plan_input, list):
        path = os.path.join(req_dir, name)
        with open(path, "w") as f:
            f.write("\n".join(str(a) for a in plan_input))
        return path

    if not isinstance(plan_input, str):
        raise FileNotFoundError(
            f"plan must be a list of action strings, a content string, or a file path; "
            f"got {type(plan_input).__name__}."
        )

    stripped = plan_input.strip()

    # Python-list-literal string: "['(pick-up a)', '(stack a b)']"
    if stripped.startswith("[") and stripped.endswith("]"):
        try:
            parsed = ast.literal_eval(stripped)
        except (SyntaxError, ValueError):
            parsed = None
        if isinstance(parsed, list) and all(isinstance(a, str) for a in parsed):
            path = os.path.join(req_dir, name)
            with open(path, "w") as f:
                f.write("\n".join(parsed))
            return path

    # Multi-line plan text — write as content so pyvalidator can attempt parse.
    # This catches both "(pick-up a)\n(stack a b)" and "pick-up a\nstack a b".
    if "\n" in plan_input:
        path = os.path.join(req_dir, name)
        with open(path, "w") as f:
            f.write(plan_input)
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


def _precondition_error_or_none(e: Exception, verbose: bool) -> dict | None:
    """Detect pyvalidator's unknown-fluent precondition-lookup exception and
    re-shape it as a structured INVALID verdict.

    pyvalidator raises (instead of returning a structured INVALID) when a plan
    references a numeric fluent the problem didn't initialize — common on
    farmland and zenotravel-numeric broken-plan fixtures. Substring match against
    pyvalidator's English message is intentionally narrow; if the upstream
    message changes (see pddl-pyvalidator), this returns None and the caller
    falls back to its generic error envelope.

    Returns the structured dict on a match, or None to let the caller decide.
    The verbose=True shape adds a `details` key so the call-site preserves its
    documented `{valid, status, report, details}` contract.
    """
    msg = str(e)
    if "does not have a value" not in msg:
        return None
    out = {
        "valid": False,
        "status": "PRECONDITION_ERROR",
        "report": msg,
    }
    if verbose:
        out["details"] = {"unknown_fluent": True, "message": msg}
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

        status is one of: "VALID", "INVALID", "SYNTAX_ERROR", "STRUCTURE_ERROR",
        or "PRECONDITION_ERROR" (numeric plan referenced an uninitialized fluent —
        precondition is unsatisfied; valid is False)."""
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
            precondition_result = _precondition_error_or_none(e, verbose)
            if precondition_result is not None:
                return precondition_result
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
        verbose=True:  {"valid": bool, "report": str, "steps": list, "trajectory": list, "details": dict}
        verbose=False: {"valid": bool, "steps": list, "trajectory": list}
                       (drops BOTH "report" and "details". This is asymmetric with
                        validate_plan, where verbose=False keeps "report".)
        Precondition:  {"valid": False, "status": "PRECONDITION_ERROR", "report": str, ...}
                       (numeric plan referenced an uninitialized fluent — verbose=True
                        adds a "details" key; steps/trajectory are not produced)
        Error:         {"error": True, "message": str}"""
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
            precondition_result = _precondition_error_or_none(e, verbose)
            if precondition_result is not None:
                return precondition_result
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
            "steps": steps,
            "trajectory": trajectory,
        }
        if verbose:
            out["report"] = result.report(verbose=True)
            out["details"] = result.to_json()
        return out


if __name__ == "__main__":
    mcp.run(transport="stdio")
