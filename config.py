from enum import Enum


class ErrorFlag(Enum):
    NO_ERROR = 0
    ERROR = -1
    FOUND_BY_SHORTEN = 0.5
    NO_SOLUTION = 1
    TIMEOUT = 2
    INVALID_PLAN = 3


PROJECT_PATH = ".."
METRIC_FF_PATH = f"{PROJECT_PATH}/METRIC_FF"
FastDownward_PATH = f"{PROJECT_PATH}/FastDownward"
