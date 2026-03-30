"""
parser_server.py — MCP server wrapping pddl-plus-parser for trajectory generation.

Pure Python (Tier 1). No Docker required.
Accepts inline PDDL content strings (starting with '(') or file paths.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, List
from mcp.server.fastmcp import FastMCP
from pydantic import Field
import os
import re
import shutil
import tempfile
import uuid

from pddl_plus_parser.exporters import TrajectoryExporter
from pddl_plus_parser.lisp_parsers import DomainParser, ProblemParser

mcp = FastMCP("pddl-parser")

# ---------------------------------------------------------------------------
# Helpers
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


if __name__ == "__main__":
    mcp.run(transport="stdio")
