"""
backends.py — PDDLBackend Protocol and canonical return-type dataclasses.

All predicate strings use PDDL s-expression format: (pred obj1 obj2)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

# ---------------------------------------------------------------------------
# Shared constants and utilities
# ---------------------------------------------------------------------------

MAX_GROUNDING_ATTEMPTS = 10_000


def parse_action_call(action_str: str) -> tuple:
    """Parse '(pick-up a)' into ('pick-up', ['a']). Returns (name, object_list)."""
    s = action_str.strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    parts = s.split()
    return parts[0], parts[1:]


def compact_pddl(s: str) -> str:
    """Collapse internal whitespace in a PDDL expression to single spaces."""
    s = re.sub(r"\s+", " ", s).strip()
    # Remove spaces before ) and after ( for canonical form
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\(\s+", "(", s)
    return s


# ---------------------------------------------------------------------------
# Canonical return types
# ---------------------------------------------------------------------------

@dataclass
class TrajectoryStep:
    """One step in a trajectory: state before + action applied."""
    state_predicates: list[str]  # sorted s-expression predicates
    action: str                  # e.g. "(pick-up a)"


@dataclass
class TrajectoryResult:
    steps: list[TrajectoryStep]
    final_state: list[str]  # sorted s-expression predicates


@dataclass
class DomainInfo:
    name: str
    requirements: list[str]
    types: dict[str, Optional[str]]       # type_name -> parent_name or None
    predicates: list[dict]                # [{"name": ..., "parameters": {param: type}}]
    actions: list[dict]                   # [{"name": ..., "parameters": ..., "precondition": ..., "effect": ...}]


@dataclass
class ProblemInfo:
    name: str
    domain_name: str
    objects: list[dict]   # [{"name": ..., "type": ...}]
    init: list[str]       # sorted s-expression predicates
    goal: list[str]       # sorted s-expression predicates


@dataclass
class ApplicabilityResult:
    applicable: bool
    satisfied_preconditions: list[str]
    unsatisfied_preconditions: list[str]
    would_add: list[str]
    would_delete: list[str]


@dataclass
class ApplicableActionsResult:
    actions: list[str]
    truncated: bool
    warning: Optional[str] = None


# ---------------------------------------------------------------------------
# Backend Protocol
# ---------------------------------------------------------------------------

class PDDLBackend(Protocol):
    name: str

    def get_trajectory(
        self, domain_path: str, problem_path: str, actions: list[str]
    ) -> TrajectoryResult: ...

    def inspect_domain(self, domain_path: str) -> DomainInfo: ...

    def inspect_problem(
        self, domain_path: str, problem_path: str
    ) -> ProblemInfo: ...

    def check_applicable(
        self,
        domain_path: str,
        problem_path: str,
        state_preds: Optional[list[str]],
        action_str: str,
    ) -> ApplicabilityResult:
        """state_preds=None means initial state."""
        ...

    def get_applicable_actions(
        self,
        domain_path: str,
        problem_path: str,
        state_preds: Optional[list[str]],
        max_results: int,
    ) -> ApplicableActionsResult:
        """state_preds=None means initial state."""
        ...
