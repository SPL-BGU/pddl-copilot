from pathlib import Path

from pddl_plus_parser.exporters import TrajectoryExporter
from pddl_plus_parser.lisp_parsers import DomainParser, ProblemParser


def create_trajectory(
    domain_file_path: Path,
    problem_file_path: Path,
    solution_file_path: Path,
) -> list[str]:
    """Creates a trajectory from the given domain, problem, and solution files.
    :param domain_file_path: the path to the domain file.
    :param problem_file_path: the path to the problem file.
    :param solution_file_path: the path to the solution file.
    :return: A list of state transitions in the trajectory, where each state is represented as a string.
    """
    domain = DomainParser(domain_file_path).parse_domain()
    trajectory_exporter = TrajectoryExporter(domain=domain)

    trajectory_file_path = (
        domain_file_path.parent / f"{solution_file_path.stem}.trajectory"
    )

    problem = ProblemParser(
        problem_path=problem_file_path, domain=domain
    ).parse_problem()

    triplets = trajectory_exporter.parse_plan(problem, solution_file_path)
    trajectory_exporter.export_to_file(triplets, trajectory_file_path)

    with open(trajectory_file_path, "r") as f:
        lines = f.readlines()
    state_transition = [line for i, line in enumerate(lines) if i % 2 == 0]

    return state_transition
