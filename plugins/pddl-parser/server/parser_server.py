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

# Try unified-planning first: it handles classical STRIPS + ADL (conditional effects,
# quantifiers, disjunctive preconditions) — the common case. Fall back to pddl-plus-parser
# for PDDL+ numeric features UP's numeric path hasn't been validated against yet.
# TODO: once UP numeric support is battle-tested on SPL-BGU domains, consider UP-only.
_BACKEND_ORDER = ["unified-planning", "pddl-plus-parser"]

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


from backends import compact_pddl, DomainInfo


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


def _extract_pddl_section(content: str, keyword: str) -> Optional[str]:
    """Extract the body of a PDDL section like (:init ...) using balanced parens."""
    idx = content.find(f"({keyword}")
    if idx == -1:
        return None
    # Find the matching closing paren
    depth = 0
    start = idx
    for i in range(idx, len(content)):
        if content[i] == '(':
            depth += 1
        elif content[i] == ')':
            depth -= 1
            if depth == 0:
                # Return everything between (keyword ... and the closing )
                inner = content[start:i + 1]
                # Strip the outer (:keyword ...) wrapper
                m = re.match(r"\(" + re.escape(keyword) + r"\s+(.*)\)$", inner, re.DOTALL)
                return m.group(1) if m else inner
    return None


def _lightweight_parse_problem(content: str) -> dict:
    """Extract structured data from a PDDL problem string without a parser.

    Works without a domain — extracts name, domain reference, objects (with
    types if present), init predicates, and goal predicates using regex.
    Cannot validate predicates or provide action info.
    """
    result = {}

    # Problem name
    m = re.search(r"\(problem\s+([^\s)]+)", content)
    result["name"] = m.group(1) if m else None

    # Domain reference
    m = re.search(r"\(:domain\s+([^\s)]+)", content)
    result["domain_name"] = m.group(1) if m else None

    # Objects — find the (:objects ...) block
    objects = []
    m = re.search(r"\(:objects\s+(.*?)\)", content, re.DOTALL)
    if m:
        obj_text = m.group(1).strip()
        # Parse typed object lists: "a b - block c - table" or untyped "a b c"
        # Split on " - " to get groups
        segments = re.split(r"\s+-\s+", obj_text)
        if len(segments) > 1:
            # Typed: each segment except last has object names, following segment starts with type name
            for i in range(len(segments) - 1):
                names = segments[i].split()
                # The type is the first token of the next segment
                next_tokens = segments[i + 1].split()
                type_name = next_tokens[0]
                for name in names:
                    name = name.strip()
                    if name:
                        objects.append({"name": name, "type": type_name})
                # Remaining tokens after type in the next segment are objects for the segment after that
                if i < len(segments) - 2:
                    segments[i + 1] = " ".join(next_tokens[1:])
        else:
            # Untyped
            for name in obj_text.split():
                name = name.strip()
                if name:
                    objects.append({"name": name, "type": "object"})
    result["objects"] = objects

    # Init predicates — extract individual (pred ...) from (:init ...)
    init_preds = []
    init_body = _extract_pddl_section(content, ":init")
    if init_body:
        init_preds = re.findall(r"\([^()]+\)", init_body)
        init_preds = [compact_pddl(p) for p in init_preds]
    result["init"] = sorted(init_preds)

    # Goal predicates — extract from (:goal ...)
    goal_preds = []
    goal_body = _extract_pddl_section(content, ":goal")
    if goal_body:
        # Unwrap outer (and ...) if present
        goal_stripped = goal_body.strip()
        and_match = re.match(r"^\(and\s+(.*)\)$", goal_stripped, re.DOTALL)
        if and_match:
            goal_stripped = and_match.group(1)
        goal_preds = re.findall(r"\([^()]+\)", goal_stripped)
        goal_preds = [compact_pddl(p) for p in goal_preds]
    result["goal"] = sorted(goal_preds)

    return result


def _domain_info_to_pddl(info: DomainInfo) -> str:
    """Reconstruct canonical PDDL domain text from a DomainInfo result."""
    lines = [f"(define (domain {info.name})"]

    if info.requirements:
        lines.append(f"  (:requirements {' '.join(info.requirements)})")

    if info.types:
        # Group types by parent (skip implicit "object" root)
        by_parent: dict = {}
        for tname, parent in info.types.items():
            if tname == "object":
                continue
            key = parent or "object"
            by_parent.setdefault(key, []).append(tname)
        type_strs = []
        for parent, children in by_parent.items():
            type_strs.append(f"{' '.join(children)} - {parent}")
        lines.append(f"  (:types {' '.join(type_strs)})")

    if info.predicates:
        pred_strs = []
        for pred in info.predicates:
            params = pred.get("parameters", {})
            if params:
                param_str = " ".join(f"{k} - {v}" for k, v in params.items())
                pred_strs.append(f"({pred['name']} {param_str})")
            else:
                pred_strs.append(f"({pred['name']})")
        lines.append(f"  (:predicates {' '.join(pred_strs)})")

    for action in info.actions:
        params = action.get("parameters", {})
        if params:
            param_str = " ".join(f"{k} - {v}" for k, v in params.items())
        else:
            param_str = ""
        lines.append(f"  (:action {action['name']}")
        lines.append(f"    :parameters ({param_str})")
        lines.append(f"    :precondition {action.get('precondition', '()')}")
        lines.append(f"    :effect {action.get('effect', '()')})")

    lines.append(")")
    return "\n".join(lines)


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
    problem: Annotated[Optional[str], Field(description="Optional PDDL problem content string or absolute file path. When provided, adds grounded details: objects, initial state, and goal.")] = None,
    parser: Annotated[Optional[str], Field(description="Parser backend: 'pddl-plus-parser', 'unified-planning', or null for auto-select with fallback.")] = None,
) -> dict:
    """Returns structured information about a PDDL domain: name, requirements, types, predicates, and actions.

    When a problem is also provided, adds grounded details: objects with types,
    initial state predicates, and goal conditions — giving a complete picture of
    the domain-scenario.

    Returns:
        Domain only: {"name": str, "requirements": [...], "types": {...}, "predicates": [...], "actions": [...], "parser_used": str}
        Domain + problem: above + {"objects": [...], "init": [...], "goal": [...], "num_objects": int, "num_init_facts": int, "num_goal_conditions": int}
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

            out = {
                "name": result.name,
                "requirements": result.requirements,
                "types": result.types,
                "predicates": result.predicates,
                "actions": result.actions,
                "parser_used": parser_used,
            }

            # If a problem is provided, add grounded details
            if problem is not None:
                try:
                    problem_path = _ensure_file(problem, "problem.pddl", rd)
                    prob_result, _ = _run_with_fallback(
                        "inspect_problem", parser, domain_path, problem_path
                    )
                    out["objects"] = prob_result.objects
                    out["init"] = prob_result.init
                    out["goal"] = prob_result.goal
                    out["num_objects"] = len(prob_result.objects)
                    out["num_init_facts"] = len(prob_result.init)
                    out["num_goal_conditions"] = len(prob_result.goal)
                except Exception as e:
                    out["problem_warning"] = f"Could not parse problem: {e}"

            return out

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
        before = set(compact_pddl(p) for p in json.loads(state_before))
        after = set(compact_pddl(p) for p in json.loads(state_after))
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
    domain: Annotated[Optional[str], Field(description="PDDL domain content string or file path. Required for full problem parsing; without it, problem parsing is partial (no action details).")] = None,
    output_format: Annotated[str, Field(description="Output format: 'pddl' for normalized PDDL text (domain only), 'json' for structured JSON.")] = "json",
) -> dict:
    """Parses PDDL content into a unified structured JSON representation.

    Accepts domain or problem content. Bridges both parser backends into a
    common JSON form.

    - **Domain content**: returns full domain structure (types, predicates, actions).
    - **Problem content + domain**: returns full problem structure via backend
      (objects, init, goal) with validation.
    - **Problem content, no domain**: lightweight regex parse — extracts objects,
      init predicates, goal predicates, and type info where available. Cannot
      validate predicates or provide action details.

    Returns:
        Success: {"valid": True, "type": "domain"|"problem", "normalized": dict|str, "warnings": [...]}
        Error: {"valid": False, "type": str, "normalized": None, "warnings": [...]}"""
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
                domain_path = _ensure_file(content, "domain.pddl", rd)
                result, parser_used = _run_with_fallback(
                    "inspect_domain", None, domain_path
                )
                if output_format == "pddl":
                    normalized = _domain_info_to_pddl(result)
                else:
                    normalized = {
                        "name": result.name,
                        "requirements": result.requirements,
                        "types": result.types,
                        "predicates": result.predicates,
                        "actions": result.actions,
                        "parser_used": parser_used,
                    }
                return {
                    "valid": True,
                    "type": "domain",
                    "normalized": normalized,
                    "warnings": [],
                }

            else:
                # Problem content
                warnings = []
                if domain is not None:
                    # Full parse with backend
                    domain_path = _ensure_file(domain, "domain.pddl", rd)
                    problem_path = _ensure_file(content, "problem.pddl", rd)
                    prob_result, parser_used = _run_with_fallback(
                        "inspect_problem", None, domain_path, problem_path
                    )
                    normalized = {
                        "name": prob_result.name,
                        "domain_name": prob_result.domain_name,
                        "objects": prob_result.objects,
                        "init": prob_result.init,
                        "goal": prob_result.goal,
                        "num_objects": len(prob_result.objects),
                        "num_init_facts": len(prob_result.init),
                        "num_goal_conditions": len(prob_result.goal),
                        "parser_used": parser_used,
                    }
                else:
                    # Lightweight parse without domain — extract what we can
                    normalized = _lightweight_parse_problem(content)
                    normalized["num_objects"] = len(normalized["objects"])
                    normalized["num_init_facts"] = len(normalized["init"])
                    normalized["num_goal_conditions"] = len(normalized["goal"])
                    warnings.append(
                        "Parsed without domain — objects, init, and goal extracted "
                        "but predicates are not validated. Action details unavailable."
                    )

                return {
                    "valid": True,
                    "type": "problem",
                    "normalized": normalized,
                    "warnings": warnings,
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
