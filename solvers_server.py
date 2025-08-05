from mcp.server.fastmcp import FastMCP
from planning import MetricFF, FastDownward, run_validate_syntax
from pathlib import Path
import time

mcp = FastMCP("Planning")


@mcp.tool()
def numeric_planner(domain: str, problem: str) -> tuple:
    """
    name: numeric_planner
    description: |
    Computes a plan for a PDDL 2.1 planning problem with numeric fluents and durative actions.
    Accepts file paths to the domain and problem definitions and returns an ordered list of actions
    that form a valid plan to achieve the goal.
    parameters:
    - name: domain
        type: string
        description: |
        File path to the PDDL 2.1 domain definition file describing predicates, durative actions,
        and numeric fluents.
    - name: problem
        type: string
        description: |
        File path to the PDDL 2.1 problem definition file specifying objects, initial state,
        goals, and optimization metrics.
    returns:
    type: tuple
    items:
        type: list, float
    description: |
        The first is :
            An ordered list of actions comprising the plan to solve the problem. Each item is the textual
            representation of an action instantiation.
        The second is the time taken to compute the plan in seconds.
    """
    t1 = time.time()
    plan = MetricFF().create_plan(domain, problem)
    t2 = time.time()
    return (plan, t2 - t1)


@mcp.tool()
def classic_planner(domain: str, problem: str) -> tuple:
    """
    name: classic_planner
    description: |
        Computes a plan for a classical PDDL planning problem.
        This planner does not support numeric fluents or durative actions — providing such features will result in an error.
        Accepts file paths to the domain and problem definitions and returns an ordered list of actions
        that form a valid plan to achieve the goal.
    parameters:
    - name: domain
      type: string
      description: |
        File path to the PDDL domain definition file describing predicates and classical actions.
    - name: problem
      type: string
      description: |
        File path to the PDDL problem definition file specifying objects, initial state, and goals.
    returns:
      type: tuple
      items:
        type: list, float
      description: |
        The first item:
            An ordered list of actions comprising the plan to solve the problem. Each item is the textual
            representation of an action instantiation.
        The second item:
            The time taken to compute the plan, in seconds.
    """
    t1 = time.time()
    plan = FastDownward().create_plan(domain, problem)
    t2 = time.time()
    return (plan, t2 - t1)


@mcp.tool()
def validate_pddl_syntax(domain: str, problem: str = None, plan: str = None) -> str:
    """
    name: validate_pddl_syntax
    description: |
        Validates the syntax and basic semantics of a PDDL domain file, and optionally a PDDL problem file,
        using the VAL Validate tool. It checks for errors such as missing predicates, type mismatches, and
        malformed actions. If a problem file is provided, it will also validate consistency between domain
        and problem files.
    parameters:
    - name: domain
      type: string
      description: |
        File path to the PDDL domain definition file containing predicates, types, and action definitions.
    - name: problem
      type: string
      description: |
        Optional File path to the PDDL problem definition file specifying objects, initial state, and goals.
        If omitted, only the domain file is validated.
    - name: plan
      type: string
      description: |
        Optional File path to the action sequance that should be validated against the domain and problem.
        If omitted, only the domain and problem files are validated.
    returns:
      type: string
      description: |
        The output from the VAL Validate tool, including any syntax or semantic errors found during validation,
        warnings, or confirmation of validity.
    """

    if problem is not None:
        problem = Path(problem).absolute()

    if plan is not None:
        plan = Path(plan).absolute()

    result = run_validate_syntax(Path(domain).absolute(), problem, plan)
    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
