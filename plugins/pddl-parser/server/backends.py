"""
backends.py — PDDLBackend Protocol and canonical return-type dataclasses.

All predicate strings use PDDL s-expression format: (pred obj1 obj2)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


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

@runtime_checkable
class PDDLBackend(Protocol):
    name: str

    def parse_domain_and_problem(
        self, domain_path: str, problem_path: str
    ) -> Any:
        """Parse domain and problem files. Returns backend-specific objects."""
        ...

    def get_trajectory(
        self, domain_path: str, problem_path: str, actions: list[str]
    ) -> TrajectoryResult:
        ...

    def inspect_domain(self, domain_path: str) -> DomainInfo:
        ...

    def inspect_problem(
        self, domain_path: str, problem_path: str
    ) -> ProblemInfo:
        ...

    def check_applicable(
        self,
        domain_path: str,
        problem_path: str,
        state_preds: Optional[list[str]],
        action_str: str,
    ) -> ApplicabilityResult:
        """Check action applicability. state_preds=None means initial state."""
        ...

    def get_applicable_actions(
        self,
        domain_path: str,
        problem_path: str,
        state_preds: Optional[list[str]],
        max_results: int,
    ) -> ApplicableActionsResult:
        """Enumerate applicable actions. state_preds=None means initial state."""
        ...

    def state_to_predicate_list(
        self, state: Any, domain_path: str, problem_path: str
    ) -> list[str]:
        """Convert a backend-specific state to sorted s-expression predicate list."""
        ...
