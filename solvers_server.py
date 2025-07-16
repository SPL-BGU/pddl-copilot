from mcp.server.fastmcp import FastMCP
from planning import MetricFF
import time

mcp = FastMCP("MAPF")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


@mcp.tool()
def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    return a * b


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


if __name__ == "__main__":
    mcp.run(transport="stdio")
