"""
parser_server.py — MCP server for PDDL introspection, trajectory generation,
applicability checking, and state analysis.

Supports multiple parser backends (pddl-plus-parser, unified-planning) with
automatic fallback. Pure Python (Tier 1). No Docker required.
Accepts inline PDDL content strings (starting with '(') or file paths.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, List, Optional
from mcp.server.fastmcp import FastMCP
from pydantic import Field
import json
import os
import re
import shutil
import tempfile
import uuid

mcp = FastMCP("pddl-parser")

# ---------------------------------------------------------------------------
# Backend initialization (lazy imports — server works with any subset)
# ---------------------------------------------------------------------------

_backends: dict = {}


def _init_backends():
    global _backends
    try:
        from backend_pddl_plus import PddlPlusBackend
        _backends["pddl-plus-parser"] = PddlPlusBackend()
    except ImportError:
        pass
    try:
        from backend_up import UnifiedPlanningBackend
        _backends["unified-planning"] = UnifiedPlanningBackend()
    except ImportError:
        pass
    if not _backends:
        raise RuntimeError("No PDDL parser backend available. Install pddl-plus-parser or unified-planning.")


_init_backends()

# Default backend order for fallback (pddl-plus-parser preferred)
_BACKEND_ORDER = ["pddl-plus-parser", "unified-planning"]

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

TEMP_DIR = os.environ.get("PDDL_TEMP_DIR", os.path.join(tempfile.gettempdir(), "pddl-parser"))
os.makedirs(TEMP_DIR, exist_ok=True)


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
    """Write PDDL content to a temp file, or resolve an existing file path."""
    stripped = content_or_path.strip()

    # Inline PDDL content — write to temp file
    if stripped.startswith("(") or stripped.startswith(";") or "(define " in stripped:
        path = os.path.join(req_dir, name)
        with open(path, "w") as f:
            f.write(content_or_path)
        return path

    # Existing file path
    if os.path.isfile(stripped):
        return os.path.abspath(stripped)

    raise FileNotFoundError(
        f"PDDL file not found: '{stripped}'. "
        f"Pass inline PDDL content (starting with '(') or a valid file path."
    )


def _clean_plan_lines(plan_path: str) -> List[str]:
    """Read a plan file and return clean action lines."""
    with open(plan_path) as f:
        lines = f.readlines()

    actions = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        line = re.sub(r"^\d+:\s*", "", line)
        line = re.sub(r"\s*;.*$", "", line).strip()
        if line:
            actions.append(line)
    return actions


def _compact_pddl(s: str) -> str:
    """Collapse internal whitespace in a PDDL expression to single spaces."""
    return re.sub(r"\s+", " ", s).strip()


def _resolve_state_preds(state_input: str) -> Optional[list[str]]:
    """Convert state input string to Optional[list[str]] for backend.

    Returns None for 'initial', or a list of predicate strings from JSON array.
    """
    if state_input.strip().lower() == "initial":
        return None
    pred_strings = json.loads(state_input)
    if not isinstance(pred_strings, list):
        raise ValueError("State must be 'initial' or a JSON array of predicate strings.")
    return pred_strings


def _format_state(preds: list[str], is_init: bool = False) -> str:
    """Format a predicate list as a PDDL state string."""
    tag = ":init" if is_init else ":state"
    return f"({tag} {' '.join(preds)})"


# ---------------------------------------------------------------------------
# Backend dispatch
# ---------------------------------------------------------------------------

def _run_with_fallback(method_name: str, parser: Optional[str], *args, **kwargs):
    """Run a backend method, optionally with fallback.

    If parser is specified, use only that backend (no fallback).
    If parser is None, try backends in order; fallback on failure.
    Returns (result, backend_name).
    """
    if parser:
        if parser not in _backends:
            available = list(_backends.keys())
            raise ValueError(f"Parser '{parser}' not available. Available: {available}")
        backend = _backends[parser]
        return getattr(backend, method_name)(*args, **kwargs), backend.name

    # Auto-select with fallback
    errors = []
    for name in _BACKEND_ORDER:
        if name not in _backends:
            continue
        backend = _backends[name]
        try:
            result = getattr(backend, method_name)(*args, **kwargs)
            return result, backend.name
        except Exception as e:
            errors.append((name, e))

    if errors:
        msg = "; ".join(f"{n}: {e}" for n, e in errors)
        raise RuntimeError(f"All parsers failed: {msg}")
    raise RuntimeError("No parser backend available.")


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def get_trajectory(
    domain: Annotated[str, Field(description="PDDL domain content string (e.g., '(define (domain ...) ...)') or absolute file path to a .pddl file.")],
    problem: Annotated[str, Field(description="PDDL problem content string or absolute file path to a .pddl file.")],
    plan: Annotated[str, Field(description="Plan content string (one action per line, e.g., '(pick-up a)\\n(stack a b)') or absolute file path.")],
    parser: Annotated[Optional[str], Field(description="Parser backend: 'pddl-plus-parser', 'unified-planning', or null for auto-select with fallback.")] = None,
) -> dict:
    """Generates a full state-action-state trajectory from a PDDL domain, problem, and plan.

    Parses the domain and problem, then simulates the plan step-by-step to produce
    structured JSON with the state before each action, the action applied, and the
    final state after all actions.

    Returns:
        Success: {"trajectory": {"1": {"state": "...", "action": "..."}, ...}, "final_state": "...", "num_steps": int, "parser_used": str}
        Error: {"error": True, "message": str}"""
    with _request_dir() as rd:
        try:
            domain_path = _ensure_file(domain, "domain.pddl", rd)
            problem_path = _ensure_file(problem, "problem.pddl", rd)
            plan_path = _ensure_file(plan, "plan.solution", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        try:
            actions = _clean_plan_lines(plan_path)
            result, parser_used = _run_with_fallback(
                "get_trajectory", parser, domain_path, problem_path, actions
            )

            if not result.steps:
                return {"trajectory": {}, "final_state": "", "num_steps": 0, "parser_used": parser_used}

            trajectory = {}
            for i, step in enumerate(result.steps):
                trajectory[str(i + 1)] = {
                    "state": _format_state(step.state_predicates, is_init=(i == 0)),
                    "action": step.action,
                }

            return {
                "trajectory": trajectory,
                "final_state": _format_state(result.final_state),
                "num_steps": len(result.steps),
                "parser_used": parser_used,
            }

        except Exception as e:
            return {"error": True, "message": f"{type(e).__name__}: {e}"}


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def inspect_domain(
    domain: Annotated[str, Field(description="PDDL domain content string (e.g., '(define (domain ...) ...)') or absolute file path to a .pddl file.")],
    parser: Annotated[Optional[str], Field(description="Parser backend: 'pddl-plus-parser', 'unified-planning', or null for auto-select with fallback.")] = None,
) -> dict:
    """Returns structured information about a PDDL domain: name, requirements, types, predicates, and actions with their parameters, preconditions, and effects.

    Returns:
        Success: {"name": str, "requirements": [...], "types": {...}, "predicates": [...], "actions": [...], "parser_used": str}
        Error: {"error": True, "message": str}"""
    with _request_dir() as rd:
        try:
            domain_path = _ensure_file(domain, "domain.pddl", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        try:
            result, parser_used = _run_with_fallback(
                "inspect_domain", parser, domain_path
            )

            return {
                "name": result.name,
                "requirements": result.requirements,
                "types": result.types,
                "predicates": result.predicates,
                "actions": result.actions,
                "parser_used": parser_used,
            }

        except Exception as e:
            return {"error": True, "message": f"{type(e).__name__}: {e}"}


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def inspect_problem(
    domain: Annotated[str, Field(description="PDDL domain content string or absolute file path.")],
    problem: Annotated[str, Field(description="PDDL problem content string or absolute file path.")],
    parser: Annotated[Optional[str], Field(description="Parser backend: 'pddl-plus-parser', 'unified-planning', or null for auto-select with fallback.")] = None,
) -> dict:
    """Returns structured information about a PDDL problem: name, objects, initial state predicates, and goal conditions.

    Returns:
        Success: {"name": str, "domain_name": str, "objects": [...], "init": [...], "goal": [...], "num_objects": int, "num_init_facts": int, "num_goal_conditions": int, "parser_used": str}
        Error: {"error": True, "message": str}"""
    with _request_dir() as rd:
        try:
            domain_path = _ensure_file(domain, "domain.pddl", rd)
            problem_path = _ensure_file(problem, "problem.pddl", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        try:
            result, parser_used = _run_with_fallback(
                "inspect_problem", parser, domain_path, problem_path
            )

            return {
                "name": result.name,
                "domain_name": result.domain_name,
                "objects": result.objects,
                "init": result.init,
                "goal": result.goal,
                "num_objects": len(result.objects),
                "num_init_facts": len(result.init),
                "num_goal_conditions": len(result.goal),
                "parser_used": parser_used,
            }

        except Exception as e:
            return {"error": True, "message": f"{type(e).__name__}: {e}"}


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def check_applicable(
    domain: Annotated[str, Field(description="PDDL domain content string or absolute file path.")],
    problem: Annotated[str, Field(description="PDDL problem content string or absolute file path.")],
    state: Annotated[str, Field(description="Either 'initial' for the initial state, or a JSON array of predicate strings (e.g., '[\"(clear a)\", \"(on a b)\"]').")],
    action: Annotated[str, Field(description="Grounded action call (e.g., '(pick-up a)' or '(stack a b)').")],
    parser: Annotated[Optional[str], Field(description="Parser backend: 'pddl-plus-parser', 'unified-planning', or null for auto-select with fallback.")] = None,
) -> dict:
    """Checks whether a grounded action is applicable in a given state, reporting satisfied/unsatisfied preconditions and the effects that would be applied.

    Returns:
        Success: {"applicable": bool, "satisfied_preconditions": [...], "unsatisfied_preconditions": [...], "would_add": [...], "would_delete": [...], "parser_used": str}
        Error: {"error": True, "message": str}"""
    with _request_dir() as rd:
        try:
            domain_path = _ensure_file(domain, "domain.pddl", rd)
            problem_path = _ensure_file(problem, "problem.pddl", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        try:
            state_preds = _resolve_state_preds(state)
            result, parser_used = _run_with_fallback(
                "check_applicable", parser,
                domain_path, problem_path, state_preds, action,
            )

            return {
                "applicable": result.applicable,
                "satisfied_preconditions": result.satisfied_preconditions,
                "unsatisfied_preconditions": result.unsatisfied_preconditions,
                "would_add": result.would_add,
                "would_delete": result.would_delete,
                "parser_used": parser_used,
            }

        except Exception as e:
            return {"error": True, "message": f"{type(e).__name__}: {e}"}


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def diff_states(
    state_before: Annotated[str, Field(description="JSON array of predicate strings for the state before (e.g., '[\"(clear a)\", \"(on a b)\"]').")],
    state_after: Annotated[str, Field(description="JSON array of predicate strings for the state after.")],
) -> dict:
    """Computes the difference between two states: which predicates were added, removed, or unchanged.

    Returns:
        Success: {"added": [...], "removed": [...], "unchanged": [...]}
        Error: {"error": True, "message": str}"""
    try:
        before = set(json.loads(state_before))
        after = set(json.loads(state_after))
    except (json.JSONDecodeError, TypeError) as e:
        return {"error": True, "message": f"Invalid JSON: {e}"}

    return {
        "added": sorted(after - before),
        "removed": sorted(before - after),
        "unchanged": sorted(before & after),
    }


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def normalize_pddl(
    content: Annotated[str, Field(description="PDDL domain or problem content string.")],
    output_format: Annotated[str, Field(description="Output format: 'pddl' for normalized PDDL text, 'json' for structured inspection.")] = "pddl",
) -> dict:
    """Parses PDDL content and re-serializes it in normalized form. Serves as a lightweight syntax check (Tier 1, no Docker/VAL required).

    Uses pddl-plus-parser exclusively (DomainExporter is parser-specific).

    Returns:
        Success: {"valid": True, "type": "domain"|"problem", "normalized": str|dict, "warnings": [...]}
        Error (parse failure): {"valid": False, "type": "unknown", "normalized": None, "warnings": [...]}"""
    with _request_dir() as rd:
        content_stripped = content.strip()

        # Detect domain vs problem
        is_domain = "(domain " in content_stripped
        is_problem = "(problem " in content_stripped
        pddl_type = "domain" if is_domain else ("problem" if is_problem else "unknown")

        if pddl_type == "unknown":
            return {
                "valid": False,
                "type": "unknown",
                "normalized": None,
                "warnings": ["Cannot detect PDDL type: content must contain '(domain ...' or '(problem ...'."],
            }

        try:
            if pddl_type == "domain":
                # normalize_pddl stays pddl-plus-parser specific
                from pddl_plus_parser.exporters import DomainExporter
                from pddl_plus_parser.lisp_parsers import DomainParser

                domain_path = _ensure_file(content, "domain.pddl", rd)
                parsed_domain = DomainParser(Path(domain_path)).parse_domain()

                if output_format == "json":
                    return {
                        "valid": True,
                        "type": "domain",
                        "normalized": inspect_domain(content),
                        "warnings": [],
                    }
                else:
                    normalized = DomainExporter().extract_domain(parsed_domain)
                    return {
                        "valid": True,
                        "type": "domain",
                        "normalized": normalized,
                        "warnings": [],
                    }
            else:
                return {
                    "valid": False,
                    "type": "problem",
                    "normalized": None,
                    "warnings": [
                        "Problem normalization requires a domain. "
                        "Use inspect_problem(domain, problem) for full problem analysis, "
                        "or pass domain content to normalize_pddl for domain normalization."
                    ],
                }

        except Exception as e:
            return {
                "valid": False,
                "type": pddl_type,
                "normalized": None,
                "warnings": [f"{type(e).__name__}: {e}"],
            }


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def get_applicable_actions(
    domain: Annotated[str, Field(description="PDDL domain content string or absolute file path.")],
    problem: Annotated[str, Field(description="PDDL problem content string or absolute file path.")],
    state: Annotated[str, Field(description="Either 'initial' for the initial state, or a JSON array of predicate strings.")] = "initial",
    max_results: Annotated[int, Field(description="Maximum number of applicable actions to return.")] = 50,
    parser: Annotated[Optional[str], Field(description="Parser backend: 'pddl-plus-parser', 'unified-planning', or null for auto-select with fallback.")] = None,
) -> dict:
    """Enumerates all applicable grounded actions in a given state by checking every possible grounding against the state's preconditions.

    Returns:
        Success: {"applicable_actions": [...], "count": int, "truncated": bool, "parser_used": str}
        Error: {"error": True, "message": str}"""
    with _request_dir() as rd:
        try:
            domain_path = _ensure_file(domain, "domain.pddl", rd)
            problem_path = _ensure_file(problem, "problem.pddl", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        try:
            state_preds = _resolve_state_preds(state)
            result, parser_used = _run_with_fallback(
                "get_applicable_actions", parser,
                domain_path, problem_path, state_preds, max_results,
            )

            out = {
                "applicable_actions": result.actions,
                "count": len(result.actions),
                "truncated": result.truncated,
                "parser_used": parser_used,
            }
            if result.warning:
                out["warning"] = result.warning
            return out

        except Exception as e:
            return {"error": True, "message": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
