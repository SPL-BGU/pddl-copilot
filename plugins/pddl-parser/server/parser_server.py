"""
parser_server.py — MCP server wrapping pddl-plus-parser for PDDL introspection,
trajectory generation, applicability checking, and state analysis.

Pure Python (Tier 1). No Docker required.
Accepts inline PDDL content strings (starting with '(') or file paths.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, List, Literal, Optional
from mcp.server.fastmcp import FastMCP
from pydantic import Field
import itertools
import json
import os
import re
import shutil
import tempfile
import uuid

from pddl_plus_parser.exporters import DomainExporter, ProblemExporter, TrajectoryExporter
from pddl_plus_parser.lisp_parsers import DomainParser, ProblemParser
from pddl_plus_parser.models.pddl_operator import Operator
from pddl_plus_parser.models.pddl_predicate import GroundedPredicate
from pddl_plus_parser.models.pddl_state import State

mcp = FastMCP("pddl-parser")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEMP_DIR = os.environ.get("PDDL_TEMP_DIR", os.path.join(tempfile.gettempdir(), "pddl-parser"))
os.makedirs(TEMP_DIR, exist_ok=True)

MAX_GROUNDING_ATTEMPTS = 10_000


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
    """Read a plan file and return clean action lines.

    Strips comments, blank lines, cost annotations, and step-number prefixes
    that planners like Fast Downward and Metric-FF add to their output.
    """
    with open(plan_path) as f:
        lines = f.readlines()

    actions = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        # Strip step-number prefix: "0: (pick-up a)" -> "(pick-up a)"
        line = re.sub(r"^\d+:\s*", "", line)
        # Strip trailing cost annotation: "(pick-up a) ; cost = 1" -> "(pick-up a)"
        line = re.sub(r"\s*;.*$", "", line).strip()
        if line:
            actions.append(line)
    return actions


def _parse_domain_and_problem(domain_str: str, problem_str: str, req_dir: str):
    """Parse domain and problem from content-or-path strings. Returns (domain, problem)."""
    domain_path = _ensure_file(domain_str, "domain.pddl", req_dir)
    problem_path = _ensure_file(problem_str, "problem.pddl", req_dir)
    parsed_domain = DomainParser(Path(domain_path)).parse_domain()
    parsed_problem = ProblemParser(
        problem_path=Path(problem_path), domain=parsed_domain
    ).parse_problem()
    return parsed_domain, parsed_problem


def _parse_action_call(action_str: str) -> tuple:
    """Parse '(pick-up a)' into ('pick-up', ['a']). Returns (name, object_list)."""
    s = action_str.strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    parts = s.split()
    return parts[0], parts[1:]


def _state_to_predicate_list(state: State) -> list:
    """Extract sorted canonical predicate list from a State object."""
    preds = []
    for grounded_set in state.state_predicates.values():
        for gp in grounded_set:
            preds.append(gp.untyped_representation)
    return sorted(preds)


def _build_initial_state(parsed_problem) -> State:
    """Construct the initial State from a parsed problem."""
    return State(
        predicates=parsed_problem.initial_state_predicates,
        fluents=parsed_problem.initial_state_fluents,
        is_init=True,
    )


def _resolve_state(state_input: str, parsed_domain, parsed_problem) -> State:
    """Resolve a state from 'initial' keyword or a JSON array of predicate strings.

    Returns a State object.
    """
    if state_input.strip().lower() == "initial":
        return _build_initial_state(parsed_problem)

    # Parse JSON array of predicate strings
    pred_strings = json.loads(state_input)
    if not isinstance(pred_strings, list):
        raise ValueError("State must be 'initial' or a JSON array of predicate strings.")

    # Group predicates by their lifted predicate representation
    state_predicates = {}
    for pred_str in pred_strings:
        s = pred_str.strip()
        if s.startswith("(") and s.endswith(")"):
            s = s[1:-1]
        parts = s.split()
        pred_name = parts[0]
        obj_names = parts[1:]

        if pred_name not in parsed_domain.predicates:
            raise ValueError(f"Unknown predicate: '{pred_name}'")

        lifted_pred = parsed_domain.predicates[pred_name]
        lifted_key = lifted_pred.untyped_representation
        param_names = list(lifted_pred.signature.keys())

        if len(param_names) != len(obj_names):
            raise ValueError(
                f"Predicate '{pred_name}' expects {len(param_names)} arguments, got {len(obj_names)}"
            )

        object_mapping = dict(zip(param_names, obj_names))
        gp = GroundedPredicate(
            name=pred_name,
            signature={k: v for k, v in lifted_pred.signature.items()},
            object_mapping=object_mapping,
            is_positive=True,
        )

        if lifted_key not in state_predicates:
            state_predicates[lifted_key] = set()
        state_predicates[lifted_key].add(gp)

    return State(predicates=state_predicates, fluents={}, is_init=False)


def _get_objects_by_type(parsed_domain, parsed_problem) -> dict:
    """Return a dict mapping type name -> list of object names (including supertypes)."""
    objects_by_type = {}
    all_objects = {**parsed_domain.constants, **parsed_problem.objects}
    for obj_name, obj in all_objects.items():
        # Add to the object's own type and all ancestor types
        current_type = obj.type
        while current_type is not None:
            type_name = current_type.name
            if type_name not in objects_by_type:
                objects_by_type[type_name] = []
            if obj_name not in objects_by_type[type_name]:
                objects_by_type[type_name].append(obj_name)
            current_type = getattr(current_type, "parent", None)
    return objects_by_type


def _compact_pddl(s: str) -> str:
    """Collapse internal whitespace in a PDDL expression to single spaces."""
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def get_trajectory(
    domain: Annotated[str, Field(description="PDDL domain content string (e.g., '(define (domain ...) ...)') or absolute file path to a .pddl file.")],
    problem: Annotated[str, Field(description="PDDL problem content string or absolute file path to a .pddl file.")],
    plan: Annotated[str, Field(description="Plan content string (one action per line, e.g., '(pick-up a)\\n(stack a b)') or absolute file path.")],
) -> dict:
    """Generates a full state-action-state trajectory from a PDDL domain, problem, and plan.

    Parses the domain and problem, then simulates the plan step-by-step to produce
    structured JSON with the state before each action, the action applied, and the
    final state after all actions.

    Returns:
        Success: {"trajectory": {"1": {"state": "...", "action": "..."}, ...}, "final_state": "...", "num_steps": int}
        Error: {"error": True, "message": str}"""
    with _request_dir() as rd:
        try:
            domain_path = _ensure_file(domain, "domain.pddl", rd)
            problem_path = _ensure_file(problem, "problem.pddl", rd)
            plan_path = _ensure_file(plan, "plan.solution", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        try:
            parsed_domain = DomainParser(Path(domain_path)).parse_domain()
            parsed_problem = ProblemParser(
                problem_path=Path(problem_path), domain=parsed_domain
            ).parse_problem()

            exporter = TrajectoryExporter(domain=parsed_domain)
            actions = _clean_plan_lines(plan_path)
            triplets = exporter.parse_plan(parsed_problem, action_sequence=actions)

            if not triplets:
                return {"trajectory": {}, "final_state": "", "num_steps": 0}

            trajectory = {}
            for i, triplet in enumerate(triplets):
                trajectory[str(i + 1)] = {
                    "state": triplet.previous_state.serialize().strip(),
                    "action": str(triplet.operator),
                }

            return {
                "trajectory": trajectory,
                "final_state": triplets[-1].next_state.serialize().strip(),
                "num_steps": len(triplets),
            }

        except Exception as e:
            return {"error": True, "message": f"{type(e).__name__}: {e}"}


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def inspect_domain(
    domain: Annotated[str, Field(description="PDDL domain content string (e.g., '(define (domain ...) ...)') or absolute file path to a .pddl file.")],
) -> dict:
    """Returns structured information about a PDDL domain: name, requirements, types, predicates, and actions with their parameters, preconditions, and effects.

    Returns:
        Success: {"name": str, "requirements": [...], "types": {...}, "predicates": [...], "actions": [...]}
        Error: {"error": True, "message": str}"""
    with _request_dir() as rd:
        try:
            domain_path = _ensure_file(domain, "domain.pddl", rd)
        except FileNotFoundError as e:
            return {"error": True, "message": str(e)}

        try:
            parsed_domain = DomainParser(Path(domain_path)).parse_domain()

            # Types: name -> parent name
            types_info = {}
            for type_name, pddl_type in parsed_domain.types.items():
                parent = getattr(pddl_type, "parent", None)
                types_info[type_name] = parent.name if parent else None

            # Predicates
            predicates_info = []
            for pred in parsed_domain.predicates.values():
                predicates_info.append({
                    "name": pred.name,
                    "parameters": {k: v.name for k, v in pred.signature.items()},
                })

            # Actions
            actions_info = []
            for action in parsed_domain.actions.values():
                actions_info.append({
                    "name": action.name,
                    "parameters": {k: v.name for k, v in action.signature.items()},
                    "precondition": _compact_pddl(str(action.preconditions)),
                    "effect": _compact_pddl(action.effects_to_pddl()),
                })

            return {
                "name": parsed_domain.name,
                "requirements": sorted(parsed_domain.requirements),
                "types": types_info,
                "predicates": predicates_info,
                "actions": actions_info,
            }

        except Exception as e:
            return {"error": True, "message": f"{type(e).__name__}: {e}"}


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def inspect_problem(
    domain: Annotated[str, Field(description="PDDL domain content string or absolute file path.")],
    problem: Annotated[str, Field(description="PDDL problem content string or absolute file path.")],
) -> dict:
    """Returns structured information about a PDDL problem: name, objects, initial state predicates, and goal conditions.

    Returns:
        Success: {"name": str, "domain_name": str, "objects": [...], "init": [...], "goal": [...], "num_objects": int, "num_init_facts": int, "num_goal_conditions": int}
        Error: {"error": True, "message": str}"""
    with _request_dir() as rd:
        try:
            parsed_domain, parsed_problem = _parse_domain_and_problem(domain, problem, rd)
        except (FileNotFoundError, Exception) as e:
            return {"error": True, "message": f"{type(e).__name__}: {e}"}

        try:
            # Objects
            objects_info = [
                {"name": name, "type": obj.type.name}
                for name, obj in parsed_problem.objects.items()
            ]

            # Initial state predicates
            init_state = _build_initial_state(parsed_problem)
            init_preds = _state_to_predicate_list(init_state)

            # Goal conditions
            goal_preds = []
            for gp in parsed_problem.goal_state_predicates:
                goal_preds.append(gp.untyped_representation)
            goal_preds.sort()

            return {
                "name": parsed_problem.name,
                "domain_name": parsed_domain.name,
                "objects": objects_info,
                "init": init_preds,
                "goal": goal_preds,
                "num_objects": len(objects_info),
                "num_init_facts": len(init_preds),
                "num_goal_conditions": len(goal_preds),
            }

        except Exception as e:
            return {"error": True, "message": f"{type(e).__name__}: {e}"}


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
def check_applicable(
    domain: Annotated[str, Field(description="PDDL domain content string or absolute file path.")],
    problem: Annotated[str, Field(description="PDDL problem content string or absolute file path.")],
    state: Annotated[str, Field(description="Either 'initial' for the initial state, or a JSON array of predicate strings (e.g., '[\"(clear a)\", \"(on a b)\"]').")],
    action: Annotated[str, Field(description="Grounded action call (e.g., '(pick-up a)' or '(stack a b)').")],
) -> dict:
    """Checks whether a grounded action is applicable in a given state, reporting satisfied/unsatisfied preconditions and the effects that would be applied.

    Returns:
        Success: {"applicable": bool, "satisfied_preconditions": [...], "unsatisfied_preconditions": [...], "would_add": [...], "would_delete": [...]}
        Error: {"error": True, "message": str}"""
    with _request_dir() as rd:
        try:
            parsed_domain, parsed_problem = _parse_domain_and_problem(domain, problem, rd)
        except (FileNotFoundError, Exception) as e:
            return {"error": True, "message": f"{type(e).__name__}: {e}"}

        try:
            resolved_state = _resolve_state(state, parsed_domain, parsed_problem)
            action_name, action_objects = _parse_action_call(action)

            if action_name not in parsed_domain.actions:
                return {"error": True, "message": f"Unknown action: '{action_name}'"}

            lifted_action = parsed_domain.actions[action_name]

            # Validate parameter count
            expected_params = len(lifted_action.signature)
            if len(action_objects) != expected_params:
                return {"error": True, "message": f"Action '{action_name}' expects {expected_params} parameters, got {len(action_objects)}"}

            operator = Operator(
                action=lifted_action,
                domain=parsed_domain,
                grounded_action_call=action_objects,
                problem_objects=parsed_problem.objects,
            )
            operator.ground()

            # Check overall applicability
            applicable = operator.is_applicable(resolved_state)

            # Collect precondition breakdown by iterating grounded preconditions
            satisfied = []
            unsatisfied = []
            state_serialized = resolved_state.serialize()
            for binary_op, condition in operator.grounded_preconditions:
                if isinstance(condition, GroundedPredicate):
                    pred_repr = condition.untyped_representation
                    # For positive preconditions, check if predicate is in state
                    # For negative preconditions, check if the positive form is absent
                    positive_copy = condition.copy()
                    positive_copy.is_positive = True
                    positive_repr = positive_copy.untyped_representation

                    if condition.is_positive:
                        if positive_repr in state_serialized:
                            satisfied.append(pred_repr)
                        else:
                            unsatisfied.append(pred_repr)
                    else:
                        # Negative precondition: satisfied if positive form is NOT in state
                        if positive_repr not in state_serialized:
                            satisfied.append(pred_repr)
                        else:
                            unsatisfied.append(pred_repr)

            # Collect effects
            would_add = []
            would_delete = []
            for effect in operator.grounded_effects:
                for gp in effect.grounded_discrete_effects:
                    if gp.is_positive:
                        would_add.append(gp.untyped_representation)
                    else:
                        # Delete effects have is_positive=False; show the positive form
                        pos = gp.copy()
                        pos.is_positive = True
                        would_delete.append(pos.untyped_representation)

            return {
                "applicable": applicable,
                "satisfied_preconditions": sorted(satisfied),
                "unsatisfied_preconditions": sorted(unsatisfied),
                "would_add": sorted(would_add),
                "would_delete": sorted(would_delete),
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
                domain_path = _ensure_file(content, "domain.pddl", rd)
                parsed_domain = DomainParser(Path(domain_path)).parse_domain()

                if output_format == "json":
                    # Reuse inspect_domain logic inline
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
                # Problem requires a domain — try to detect and parse domain from content
                # For normalize_pddl, we only handle standalone problem content
                # when the domain is embedded or we just validate parse-ability
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
) -> dict:
    """Enumerates all applicable grounded actions in a given state by checking every possible grounding against the state's preconditions.

    Returns:
        Success: {"applicable_actions": [...], "count": int, "truncated": bool}
        Error: {"error": True, "message": str}"""
    with _request_dir() as rd:
        try:
            parsed_domain, parsed_problem = _parse_domain_and_problem(domain, problem, rd)
        except (FileNotFoundError, Exception) as e:
            return {"error": True, "message": f"{type(e).__name__}: {e}"}

        try:
            resolved_state = _resolve_state(state, parsed_domain, parsed_problem)
            objects_by_type = _get_objects_by_type(parsed_domain, parsed_problem)

            applicable = []
            total_groundings = 0
            truncated = False
            grounding_cap_hit = False

            for action in parsed_domain.actions.values():
                if len(applicable) >= max_results:
                    truncated = True
                    break

                param_types = list(action.signature.values())
                if not param_types:
                    # Zero-arity action
                    total_groundings += 1
                    operator = Operator(
                        action=action,
                        domain=parsed_domain,
                        grounded_action_call=[],
                        problem_objects=parsed_problem.objects,
                    )
                    if operator.is_applicable(resolved_state):
                        applicable.append(f"({action.name})")
                        if len(applicable) >= max_results:
                            truncated = True
                            break
                    continue

                # Get object lists for each parameter type
                obj_lists = []
                for ptype in param_types:
                    objs = objects_by_type.get(ptype.name, [])
                    obj_lists.append(objs)

                if not all(obj_lists):
                    continue

                for combo in itertools.product(*obj_lists):
                    total_groundings += 1
                    if total_groundings > MAX_GROUNDING_ATTEMPTS:
                        grounding_cap_hit = True
                        break

                    obj_list = list(combo)
                    operator = Operator(
                        action=action,
                        domain=parsed_domain,
                        grounded_action_call=obj_list,
                        problem_objects=parsed_problem.objects,
                    )
                    try:
                        if operator.is_applicable(resolved_state):
                            applicable.append(f"({action.name} {' '.join(obj_list)})")
                            if len(applicable) >= max_results:
                                truncated = True
                                break
                    except Exception:
                        # Skip groundings that cause errors (e.g., type mismatches)
                        continue

                if grounding_cap_hit or truncated:
                    break

            result = {
                "applicable_actions": applicable,
                "count": len(applicable),
                "truncated": truncated or grounding_cap_hit,
            }
            if grounding_cap_hit:
                result["warning"] = f"Grounding attempt cap ({MAX_GROUNDING_ATTEMPTS}) reached. Results may be incomplete."

            return result

        except Exception as e:
            return {"error": True, "message": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
