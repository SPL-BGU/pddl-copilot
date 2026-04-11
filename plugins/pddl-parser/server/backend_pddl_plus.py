"""
backend_pddl_plus.py — PDDLBackend implementation using pddl-plus-parser.

Extracted from parser_server.py. All predicate strings use s-expression format.
"""

from pathlib import Path
from typing import Optional
import itertools
import os
import re
import sys
import tempfile

from pddl_plus_parser.exporters import TrajectoryExporter
from pddl_plus_parser.lisp_parsers import DomainParser, ProblemParser
from pddl_plus_parser.models.pddl_operator import Operator
from pddl_plus_parser.models.pddl_predicate import GroundedPredicate
from pddl_plus_parser.models.pddl_state import State

from backends import (
    MAX_GROUNDING_ATTEMPTS,
    ApplicabilityResult,
    ApplicableActionsResult,
    DomainInfo,
    ProblemInfo,
    TrajectoryResult,
    TrajectoryStep,
    canonicalize_action,
    compact_pddl,
    normalize_action_input,
    suggest_close_match,
)


_PRECOND_CONNECTIVES = frozenset(("and", "or", "not", "forall", "exists", "imply", "when"))
_PRECOND_KEYWORD = re.compile(r":precondition\b", re.IGNORECASE)
_HEAD_TOKEN = re.compile(r"\(\s*([A-Za-z][A-Za-z0-9_\-]*)")


def _wrap_bare_preconditions(text: str) -> str:
    """Wrap atomic :precondition literals in (and ...).

    Upstream pddl-plus-parser has a bug where a bare :precondition (P ...)
    is silently dropped and the parser returns an empty conjunction, which
    stringifies back to "(and )". Wrapping atomic literals as (and (P ...))
    keeps the precondition intact without touching the library.
    """
    out = []
    pos = 0
    while pos < len(text):
        m = _PRECOND_KEYWORD.search(text, pos)
        if not m:
            out.append(text[pos:])
            break
        out.append(text[pos:m.end()])
        i = m.end()
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text) or text[i] != "(":
            pos = i
            continue

        start = i
        depth = 0
        j = i
        while j < len(text):
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth != 0:
            out.append(text[i:])
            break

        sexpr = text[start:j + 1]
        out.append(text[m.end():start])

        head = _HEAD_TOKEN.match(sexpr)
        if head and head.group(1).lower() in _PRECOND_CONNECTIVES:
            out.append(sexpr)
        else:
            out.append(f"(and {sexpr})")
        pos = j + 1
    return "".join(out)


class PddlPlusBackend:
    name = "pddl-plus-parser"

    # -- internal helpers --------------------------------------------------

    def _parse(self, domain_path: str, problem_path: str):
        parsed_domain = self._parse_domain_wrapped(domain_path)
        parsed_problem = ProblemParser(
            problem_path=Path(problem_path), domain=parsed_domain
        ).parse_problem()
        return parsed_domain, parsed_problem

    def _parse_domain_only(self, domain_path: str):
        return self._parse_domain_wrapped(domain_path)

    @staticmethod
    def _parse_domain_wrapped(domain_path: str):
        """Parse a domain after pre-wrapping bare preconditions. Writes a
        sibling temp file in the same directory so any relative :include
        references resolve, and cleans it up afterwards."""
        try:
            with open(domain_path, encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError):
            return DomainParser(Path(domain_path)).parse_domain()

        wrapped = _wrap_bare_preconditions(content)
        if wrapped == content:
            return DomainParser(Path(domain_path)).parse_domain()

        parent = Path(domain_path).parent
        fd, tmp_path = tempfile.mkstemp(suffix=".pddl", dir=str(parent))
        try:
            with os.fdopen(fd, "w") as f:
                f.write(wrapped)
            return DomainParser(Path(tmp_path)).parse_domain()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @staticmethod
    def _build_initial_state(parsed_problem) -> State:
        return State(
            predicates=parsed_problem.initial_state_predicates,
            fluents=parsed_problem.initial_state_fluents,
            is_init=True,
        )

    @staticmethod
    def _state_to_preds(state: State) -> list[str]:
        preds = []
        for grounded_set in state.state_predicates.values():
            for gp in grounded_set:
                preds.append(compact_pddl(gp.untyped_representation))
        return sorted(preds)

    def _resolve_state(
        self,
        state_preds: Optional[list[str]],
        parsed_domain,
        parsed_problem,
    ) -> State:
        if state_preds is None:
            return self._build_initial_state(parsed_problem)

        state_predicates = {}
        for pred_str in state_preds:
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
                    f"Predicate '{pred_name}' expects {len(param_names)} arguments, "
                    f"got {len(obj_names)}"
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

    @staticmethod
    def _get_objects_by_type(parsed_domain, parsed_problem) -> dict:
        objects_by_type: dict[str, set] = {}
        all_objects = {**parsed_domain.constants, **parsed_problem.objects}
        for obj_name, obj in all_objects.items():
            current_type = obj.type
            while current_type is not None:
                type_name = current_type.name
                if type_name not in objects_by_type:
                    objects_by_type[type_name] = set()
                objects_by_type[type_name].add(obj_name)
                current_type = getattr(current_type, "parent", None)
        return {k: list(v) for k, v in objects_by_type.items()}

    # -- Protocol methods --------------------------------------------------

    def get_trajectory(
        self, domain_path: str, problem_path: str, actions: list[str]
    ) -> TrajectoryResult:
        parsed_domain, parsed_problem = self._parse(domain_path, problem_path)

        canonical_actions = []
        for a in actions:
            name, args = normalize_action_input(a)
            if name not in parsed_domain.actions:
                lowered = name.lower()
                for real_name in parsed_domain.actions:
                    if real_name.lower() == lowered:
                        name = real_name
                        break
            canonical_actions.append(canonicalize_action(name, args))

        exporter = TrajectoryExporter(domain=parsed_domain)
        triplets = exporter.parse_plan(parsed_problem, action_sequence=canonical_actions)

        if not triplets:
            return TrajectoryResult(steps=[], final_state=[])

        steps = []
        for triplet in triplets:
            steps.append(TrajectoryStep(
                state_predicates=self._state_to_preds(triplet.previous_state),
                action=str(triplet.operator),
            ))

        return TrajectoryResult(
            steps=steps,
            final_state=self._state_to_preds(triplets[-1].next_state),
        )

    def inspect_domain(self, domain_path: str) -> DomainInfo:
        parsed_domain = self._parse_domain_only(domain_path)

        types_info = {}
        for type_name, pddl_type in parsed_domain.types.items():
            parent = getattr(pddl_type, "parent", None)
            types_info[type_name] = parent.name if parent else None

        predicates_info = []
        for pred in parsed_domain.predicates.values():
            predicates_info.append({
                "name": pred.name,
                "parameters": {k: v.name for k, v in pred.signature.items()},
            })

        actions_info = []
        for action in parsed_domain.actions.values():
            actions_info.append({
                "name": action.name,
                "parameters": {k: v.name for k, v in action.signature.items()},
                "precondition": compact_pddl(str(action.preconditions)),
                "effect": compact_pddl(action.effects_to_pddl()),
            })

        return DomainInfo(
            name=parsed_domain.name,
            requirements=sorted(parsed_domain.requirements),
            types=types_info,
            predicates=predicates_info,
            actions=actions_info,
        )

    def inspect_problem(
        self, domain_path: str, problem_path: str
    ) -> ProblemInfo:
        parsed_domain, parsed_problem = self._parse(domain_path, problem_path)

        objects_info = [
            {"name": name, "type": obj.type.name}
            for name, obj in parsed_problem.objects.items()
        ]

        init_state = self._build_initial_state(parsed_problem)
        init_preds = self._state_to_preds(init_state)

        goal_preds = []
        for gp in parsed_problem.goal_state_predicates:
            goal_preds.append(compact_pddl(gp.untyped_representation))
        goal_preds.sort()

        return ProblemInfo(
            name=parsed_problem.name,
            domain_name=parsed_domain.name,
            objects=objects_info,
            init=init_preds,
            goal=goal_preds,
        )

    def check_applicable(
        self,
        domain_path: str,
        problem_path: str,
        state_preds: Optional[list[str]],
        action_str: str,
    ) -> ApplicabilityResult:
        parsed_domain, parsed_problem = self._parse(domain_path, problem_path)
        resolved_state = self._resolve_state(state_preds, parsed_domain, parsed_problem)
        action_name, action_objects = normalize_action_input(action_str)

        lifted_action = parsed_domain.actions.get(action_name)
        if lifted_action is None:
            lowered = action_name.lower()
            for real_name, action in parsed_domain.actions.items():
                if real_name.lower() == lowered:
                    lifted_action = action
                    action_name = real_name
                    break
        if lifted_action is None:
            suggestion = suggest_close_match(action_name, list(parsed_domain.actions.keys()))
            raise ValueError(f"Unknown action: '{action_name}'.{suggestion}")

        expected_params = len(lifted_action.signature)
        if len(action_objects) != expected_params:
            raise ValueError(
                f"Action '{action_name}' expects {expected_params} parameters, "
                f"got {len(action_objects)}"
            )

        operator = Operator(
            action=lifted_action,
            domain=parsed_domain,
            grounded_action_call=action_objects,
            problem_objects=parsed_problem.objects,
        )
        operator.ground()

        applicable = operator.is_applicable(resolved_state)

        satisfied = []
        unsatisfied = []
        state_serialized = resolved_state.serialize()
        for binary_op, condition in operator.grounded_preconditions:
            if isinstance(condition, GroundedPredicate):
                pred_repr = compact_pddl(condition.untyped_representation)
                positive_copy = condition.copy()
                positive_copy.is_positive = True
                positive_repr = positive_copy.untyped_representation

                if condition.is_positive:
                    if positive_repr in state_serialized:
                        satisfied.append(pred_repr)
                    else:
                        unsatisfied.append(pred_repr)
                else:
                    if positive_repr not in state_serialized:
                        satisfied.append(pred_repr)
                    else:
                        unsatisfied.append(pred_repr)

        would_add = []
        would_delete = []
        for effect in operator.grounded_effects:
            for gp in effect.grounded_discrete_effects:
                if gp.is_positive:
                    would_add.append(compact_pddl(gp.untyped_representation))
                else:
                    pos = gp.copy()
                    pos.is_positive = True
                    would_delete.append(compact_pddl(pos.untyped_representation))

        return ApplicabilityResult(
            applicable=applicable,
            satisfied_preconditions=sorted(satisfied),
            unsatisfied_preconditions=sorted(unsatisfied),
            would_add=sorted(would_add),
            would_delete=sorted(would_delete),
        )

    def get_applicable_actions(
        self,
        domain_path: str,
        problem_path: str,
        state_preds: Optional[list[str]],
        max_results: int,
    ) -> ApplicableActionsResult:
        parsed_domain, parsed_problem = self._parse(domain_path, problem_path)
        resolved_state = self._resolve_state(state_preds, parsed_domain, parsed_problem)
        objects_by_type = self._get_objects_by_type(parsed_domain, parsed_problem)

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
                except (AttributeError, ValueError, TypeError, KeyError) as e:
                    print(f"Warning: grounding {action.name} with {obj_list} failed: {e}", file=sys.stderr)
                    continue

            if grounding_cap_hit or truncated:
                break

        warning = None
        if grounding_cap_hit:
            warning = f"Grounding attempt cap ({MAX_GROUNDING_ATTEMPTS}) reached. Results may be incomplete."

        return ApplicableActionsResult(
            actions=applicable,
            truncated=truncated or grounding_cap_hit,
            warning=warning,
        )

