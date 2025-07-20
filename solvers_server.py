from mcp.server.fastmcp import FastMCP
from planning import MetricFF, FastDownward
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


if __name__ == "__main__":
    mcp.run(transport="stdio")
