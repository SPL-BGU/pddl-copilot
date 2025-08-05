import config as CONFIG

import os
import subprocess
from pathlib import Path


def run_validate_syntax(
    domain_file_path: Path,
    problem_file_path: Path = None,
    solution_file_path: Path = None,
) -> str:
    """Validates that the plan for the input problem.

    :param domain_file_path: the path to the domain file.
    :param problem_file_path: the path to the problem file.
    :param solution_file_path: the path to the solution file.
    :return: A string indicating the result of the validation."""

    original_dir = os.getcwd()
    os.chdir(CONFIG.VALIDATOR_DIRECTORY)

    validation_file_path = domain_file_path.parent / "validation_log.txt"
    run_command = f"./Validate -v -t 0.1 {domain_file_path} {problem_file_path} {solution_file_path}"

    with open(validation_file_path, "w") as output_file:
        retcode = subprocess.call(
            run_command, shell=True, stdout=output_file, stderr=output_file
        )
    os.chdir(original_dir)

    with open(validation_file_path, "r") as validation_file:
        validation_file_content = validation_file.read()

    return f"retcode {retcode}\n {validation_file_content}"
