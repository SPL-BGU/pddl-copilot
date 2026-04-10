"""
backend_up.py — PDDLBackend implementation using unified-planning.

All predicate strings use PDDL s-expression format: (pred obj1 obj2)
"""

import itertools
import os
import re
import shutil
import sys
import tempfile
from typing import Any, Optional

from unified_planning.io import PDDLReader
from unified_planning.model.state import UPState
from unified_planning.shortcuts import SequentialSimulator
from unified_planning.plans import ActionInstance

from backends import (
    MAX_GROUNDING_ATTEMPTS,
    ApplicabilityResult,
    ApplicableActionsResult,
    DomainInfo,
    ProblemInfo,
    TrajectoryResult,
    TrajectoryStep,
    normalize_action_input,
    suggest_close_match,
)


class UnifiedPlanningBackend:
    name = "unified-planning"

    # -- internal helpers --------------------------------------------------

    @staticmethod
    def _type_matches(obj_type, param_type) -> bool:
        try:
            return obj_type == param_type or param_type.is_compatible(obj_type)
        except AttributeError:
            return obj_type == param_type

    @staticmethod
    def _get_object_combinations(fluent, up_problem):
        param_types = [param.type for param in fluent.signature]
        object_lists = []
        for req_type in param_types:
            matching = [
                obj for obj in up_problem.all_objects
                if UnifiedPlanningBackend._type_matches(obj.type, req_type)
            ]
            object_lists.append(matching)
        return itertools.product(*object_lists)

    @staticmethod
    def _state_to_preds(state, up_problem) -> list[str]:
        """Convert UP state to sorted s-expression predicate list."""
        preds = []
        for fluent in up_problem.fluents:
            if fluent.arity == 0:
                try:
                    if state.get_value(fluent()).bool_constant_value():
                        preds.append(f"({fluent.name})")
                except (AttributeError, ValueError):
                    continue
            else:
                for combo in UnifiedPlanningBackend._get_object_combinations(fluent, up_problem):
                    try:
                        fluent_expr = fluent(*combo)
                        if state.get_value(fluent_expr).bool_constant_value():
                            obj_names = " ".join(obj.name for obj in combo)
                            preds.append(f"({fluent.name} {obj_names})")
                    except (AttributeError, ValueError):
                        continue
        return sorted(preds)

    @staticmethod
    def _find_action_schema(up_problem, action_name: str):
        for action in up_problem.actions:
            if action.name == action_name:
                return action
        lowered = action_name.lower()
        for action in up_problem.actions:
            if action.name.lower() == lowered:
                return action
        suggestion = suggest_close_match(action_name, [a.name for a in up_problem.actions])
        raise ValueError(f"Unknown action: '{action_name}'.{suggestion}")

    @staticmethod
    def _resolve_parameters(up_problem, param_names: list[str], schema=None):
        if schema is not None:
            expected = len(schema.parameters)
            if len(param_names) != expected:
                raise ValueError(
                    f"Action '{schema.name}' expects {expected} parameters, "
                    f"got {len(param_names)}"
                )
        param_objects = []
        for pname in param_names:
            found = None
            for obj in up_problem.all_objects:
                if obj.name == pname:
                    found = obj
                    break
            if found is None:
                lowered = pname.lower()
                for obj in up_problem.all_objects:
                    if obj.name.lower() == lowered:
                        found = obj
                        break
            if found is None:
                suggestion = suggest_close_match(pname, [o.name for o in up_problem.all_objects])
                raise ValueError(f"Object '{pname}' not found in problem.{suggestion}")
            param_objects.append(found)
        return param_objects

    def _build_state_from_preds(self, state_preds: list[str], up_problem, simulator):
        """Reconstruct a UP state from a predicate string list.

        Builds a values dict mapping every fluent grounding to True/False,
        then constructs a UPState.
        """
        pred_set = set(state_preds)

        # Get expression manager for True/False constants
        env = up_problem.environment
        em = env.expression_manager
        true_val = em.TRUE()
        false_val = em.FALSE()

        values = {}
        for fluent in up_problem.fluents:
            if fluent.arity == 0:
                key = f"({fluent.name})"
                expr = fluent()
                values[expr] = true_val if key in pred_set else false_val
            else:
                for combo in self._get_object_combinations(fluent, up_problem):
                    obj_names = " ".join(obj.name for obj in combo)
                    key = f"({fluent.name} {obj_names})"
                    expr = fluent(*combo)
                    values[expr] = true_val if key in pred_set else false_val

        return UPState(values, up_problem)

    def _resolve_state(self, state_preds, up_problem, simulator):
        if state_preds is None:
            return simulator.get_initial_state()
        return self._build_state_from_preds(state_preds, up_problem, simulator)

    def _fnode_to_pddl(self, expr, action_schema=None, binding=None) -> str:
        """Convert a UP FNode expression to PDDL s-expression string.

        For lifted expressions (preconditions): uses parameter names.
        For grounded expressions: uses object names from binding.
        """
        if hasattr(expr, 'is_and') and expr.is_and():
            parts = [self._fnode_to_pddl(a, action_schema, binding) for a in expr.args]
            return f"(and {' '.join(parts)})"

        if hasattr(expr, 'is_or') and expr.is_or():
            parts = [self._fnode_to_pddl(a, action_schema, binding) for a in expr.args]
            return f"(or {' '.join(parts)})"

        if hasattr(expr, 'is_not') and expr.is_not():
            inner = self._fnode_to_pddl(expr.args[0], action_schema, binding)
            return f"(not {inner})"

        if hasattr(expr, 'is_implies') and expr.is_implies():
            antecedent = self._fnode_to_pddl(expr.args[0], action_schema, binding)
            consequent = self._fnode_to_pddl(expr.args[1], action_schema, binding)
            return f"(imply {antecedent} {consequent})"

        if hasattr(expr, 'is_equals') and expr.is_equals():
            left = self._fnode_to_pddl(expr.args[0], action_schema, binding)
            right = self._fnode_to_pddl(expr.args[1], action_schema, binding)
            return f"(= {left} {right})"

        if hasattr(expr, 'is_exists') and expr.is_exists():
            vars_list = expr.variables()
            var_strs = []
            for v in vars_list:
                vtype = v.type.name if hasattr(v.type, 'name') else str(v.type)
                var_strs.append(f"?{v.name} - {vtype}")
            body = self._fnode_to_pddl(expr.args[0], action_schema, binding)
            return f"(exists ({' '.join(var_strs)}) {body})"

        if hasattr(expr, 'is_forall') and expr.is_forall():
            vars_list = expr.variables()
            var_strs = []
            for v in vars_list:
                vtype = v.type.name if hasattr(v.type, 'name') else str(v.type)
                var_strs.append(f"?{v.name} - {vtype}")
            body = self._fnode_to_pddl(expr.args[0], action_schema, binding)
            return f"(forall ({' '.join(var_strs)}) {body})"

        if hasattr(expr, 'is_parameter_exp') and expr.is_parameter_exp():
            param = expr.parameter()
            if binding and param.name in binding:
                return binding[param.name].name
            return f"?{param.name}"

        if hasattr(expr, 'is_object_exp') and expr.is_object_exp():
            return expr.object().name

        if hasattr(expr, 'is_fluent_exp') and expr.is_fluent_exp():
            fluent = expr.fluent()
            if expr.args:
                arg_strs = []
                for arg in expr.args:
                    # Recurse to handle parameter_exp, object_exp, etc.
                    arg_strs.append(self._fnode_to_pddl(arg, action_schema, binding))
                return f"({fluent.name} {' '.join(arg_strs)})"
            else:
                return f"({fluent.name})"

        print(f"Warning: unhandled FNode type in _fnode_to_pddl: {type(expr).__name__}", file=sys.stderr)
        return str(expr)

    def _make_binding(self, action_schema, param_objects) -> dict:
        """Create a parameter-name -> object mapping for grounding expressions."""
        binding = {}
        for param, obj in zip(action_schema.parameters, param_objects):
            binding[param.name] = obj
        return binding

    @staticmethod
    def _ground_expression(expr, schema, param_objects, up_problem):
        """Substitute action parameters with concrete objects in an FNode."""
        em = up_problem.environment.expression_manager
        subs = {}
        for param, obj in zip(schema.parameters, param_objects):
            subs[em.ParameterExp(param)] = em.ObjectExp(obj)
        return expr.substitute(subs)

    @staticmethod
    def _flatten_preconditions(preconditions):
        """Recursively flatten compound AND preconditions into atomic expressions."""
        flat = []
        for precond in preconditions:
            flat.extend(UnifiedPlanningBackend._flatten_and(precond))
        return flat

    @staticmethod
    def _flatten_and(expr):
        """Recursively extract conjuncts from AND expressions."""
        if hasattr(expr, 'is_and') and expr.is_and():
            result = []
            for arg in expr.args:
                result.extend(UnifiedPlanningBackend._flatten_and(arg))
            return result
        return [expr]

    # -- Protocol methods --------------------------------------------------

    def _parse(self, domain_path: str, problem_path: str) -> Any:
        reader = PDDLReader()
        return reader.parse_problem(domain_path, problem_path)

    def get_trajectory(
        self, domain_path: str, problem_path: str, actions: list[str]
    ) -> TrajectoryResult:
        up_problem = self._parse(domain_path, problem_path)
        simulator = SequentialSimulator(up_problem)
        state = simulator.get_initial_state()

        steps = []
        for action_str in actions:
            state_preds = self._state_to_preds(state, up_problem)
            action_name, param_names = normalize_action_input(action_str)

            schema = self._find_action_schema(up_problem, action_name)
            param_objects = self._resolve_parameters(up_problem, param_names, schema)
            instance = ActionInstance(schema, tuple(param_objects))

            if not simulator.is_applicable(state, instance):
                raise RuntimeError(
                    f"Action {action_str} is not applicable in the current state"
                )

            steps.append(TrajectoryStep(
                state_predicates=state_preds,
                action=action_str,
            ))
            state = simulator.apply(state, instance)

        final = self._state_to_preds(state, up_problem)
        return TrajectoryResult(steps=steps, final_state=final)

    def inspect_domain(self, domain_path: str) -> DomainInfo:
        # UP requires both domain and problem to parse. Create a synthetic problem.
        domain_name = self._extract_domain_name(domain_path)

        dummy_problem = (
            f"(define (problem dummy) (:domain {domain_name}) "
            f"(:init) (:goal (and)))"
        )
        tmp_dir = tempfile.mkdtemp(prefix="up-inspect-")
        try:
            dummy_path = os.path.join(tmp_dir, "problem.pddl")
            with open(dummy_path, "w") as f:
                f.write(dummy_problem)

            up_problem = self._parse(domain_path, dummy_path)
            return self._extract_domain_info(up_problem, domain_name, domain_path)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _get_domain_constant_names(self, domain_path: str) -> set[str]:
        """Get names of domain constants by parsing domain with an empty problem."""
        domain_name = self._extract_domain_name(domain_path)
        dummy = f"(define (problem dc) (:domain {domain_name}) (:init) (:goal (and)))"
        tmp_dir = tempfile.mkdtemp(prefix="up-dc-")
        try:
            dp = os.path.join(tmp_dir, "problem.pddl")
            with open(dp, "w") as f:
                f.write(dummy)
            dummy_problem = self._parse(domain_path, dp)
            return {obj.name for obj in dummy_problem.all_objects}
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def inspect_problem(
        self, domain_path: str, problem_path: str
    ) -> ProblemInfo:
        up_problem = self._parse(domain_path, problem_path)
        simulator = SequentialSimulator(up_problem)
        init_state = simulator.get_initial_state()
        init_preds = self._state_to_preds(init_state, up_problem)

        # Filter to problem objects only (exclude domain constants)
        domain_constants = self._get_domain_constant_names(domain_path)
        objects_info = []
        for obj in up_problem.all_objects:
            if obj.name in domain_constants:
                continue
            type_name = obj.type.name if hasattr(obj.type, 'name') else str(obj.type)
            objects_info.append({"name": obj.name, "type": type_name})

        goal_preds = []
        for goal in up_problem.goals:
            goal_preds.append(self._fnode_to_pddl(goal))
        goal_preds.sort()

        domain_name = self._extract_domain_name(domain_path)
        return ProblemInfo(
            name=up_problem.name,
            domain_name=domain_name,
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
        from unified_planning.model.walkers.state_evaluator import StateEvaluator

        up_problem = self._parse(domain_path, problem_path)
        simulator = SequentialSimulator(up_problem)
        state = self._resolve_state(state_preds, up_problem, simulator)

        action_name, param_names = normalize_action_input(action_str)
        schema = self._find_action_schema(up_problem, action_name)
        param_objects = self._resolve_parameters(up_problem, param_names, schema)
        instance = ActionInstance(schema, tuple(param_objects))
        applicable = simulator.is_applicable(state, instance)
        binding = self._make_binding(schema, param_objects)
        se = StateEvaluator(up_problem)

        # Precondition breakdown — evaluate each against state
        state_pred_set = set(self._state_to_preds(state, up_problem))
        satisfied = []
        unsatisfied = []
        for precond in self._flatten_preconditions(schema.preconditions):
            grounded_str = self._fnode_to_pddl(precond, schema, binding)
            grounded_expr = self._ground_expression(
                precond, schema, param_objects, up_problem
            )
            try:
                if se.evaluate(grounded_expr, state).bool_constant_value():
                    satisfied.append(grounded_str)
                else:
                    unsatisfied.append(grounded_str)
            except (AttributeError, ValueError, TypeError):
                # Fallback: string-based check for simple atomic predicates
                is_neg = hasattr(precond, 'is_not') and precond.is_not()
                if is_neg:
                    inner_str = self._fnode_to_pddl(precond.args[0], schema, binding)
                    if inner_str not in state_pred_set:
                        satisfied.append(grounded_str)
                    else:
                        unsatisfied.append(grounded_str)
                else:
                    if grounded_str in state_pred_set:
                        satisfied.append(grounded_str)
                    else:
                        unsatisfied.append(grounded_str)

        # Effect breakdown — respect conditional effects
        would_add = []
        would_delete = []
        for effect in schema.effects:
            if effect.is_conditional():
                grounded_cond = self._ground_expression(
                    effect.condition, schema, param_objects, up_problem
                )
                try:
                    if not se.evaluate(grounded_cond, state).bool_constant_value():
                        continue
                except (AttributeError, ValueError, TypeError):
                    continue
            fluent_str = self._fnode_to_pddl(effect.fluent, schema, binding)
            if effect.value.is_true():
                would_add.append(fluent_str)
            elif effect.value.is_false():
                would_delete.append(fluent_str)

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
        up_problem = self._parse(domain_path, problem_path)
        simulator = SequentialSimulator(up_problem)
        state = self._resolve_state(state_preds, up_problem, simulator)

        applicable = []
        total_groundings = 0
        truncated = False
        grounding_cap_hit = False

        for action in up_problem.actions:
            if len(applicable) >= max_results:
                truncated = True
                break

            params = action.parameters
            if not params:
                total_groundings += 1
                instance = ActionInstance(action, tuple())
                try:
                    if simulator.is_applicable(state, instance):
                        applicable.append(f"({action.name})")
                        if len(applicable) >= max_results:
                            truncated = True
                            break
                except (AttributeError, ValueError, TypeError, KeyError) as e:
                    print(f"Warning: grounding {action.name}() failed: {e}", file=sys.stderr)
                continue

            # Build object lists per parameter type
            obj_lists = []
            for param in params:
                matching = [
                    obj for obj in up_problem.all_objects
                    if self._type_matches(obj.type, param.type)
                ]
                obj_lists.append(matching)

            if not all(obj_lists):
                continue

            for combo in itertools.product(*obj_lists):
                total_groundings += 1
                if total_groundings > MAX_GROUNDING_ATTEMPTS:
                    grounding_cap_hit = True
                    break

                instance = ActionInstance(action, combo)
                try:
                    if simulator.is_applicable(state, instance):
                        obj_names = " ".join(obj.name for obj in combo)
                        applicable.append(f"({action.name} {obj_names})")
                        if len(applicable) >= max_results:
                            truncated = True
                            break
                except (AttributeError, ValueError, TypeError, KeyError) as e:
                    print(f"Warning: grounding {action.name} with {combo} failed: {e}", file=sys.stderr)
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

    # -- domain introspection helpers --------------------------------------

    @staticmethod
    def _extract_domain_name(domain_path: str) -> str:
        """Extract domain name from PDDL file using regex."""
        with open(domain_path) as f:
            content = f.read()
        match = re.search(r"\(domain\s+([^\s)]+)", content)
        if match:
            return match.group(1)
        return "_unknown"

    @staticmethod
    def _extract_requirements_from_pddl(domain_path: str) -> Optional[list[str]]:
        """Extract requirements from PDDL domain file via regex."""
        with open(domain_path) as f:
            content = f.read()
        m = re.search(r'\(:requirements\s+(.*?)\)', content, re.DOTALL)
        if not m:
            return None
        return sorted(m.group(1).split())

    def _extract_domain_info(self, up_problem, domain_name: str = None, domain_path: str = None) -> DomainInfo:
        """Extract domain-level info from a parsed UP problem."""
        # Types — align parent naming with pddl-plus-parser
        types_info = {}
        for user_type in up_problem.user_types:
            type_name = str(user_type.name) if hasattr(user_type, 'name') else str(user_type)
            parent = None
            if hasattr(user_type, 'father') and user_type.father:
                parent = str(user_type.father.name) if hasattr(user_type.father, 'name') else str(user_type.father)
            # Root user types implicitly inherit from "object"
            if parent is None:
                parent = "object"
            types_info[type_name] = parent
        # Include implicit "object" root type for parity with pddl-plus
        if types_info and "object" not in types_info:
            types_info["object"] = None

        # Predicates (from fluents)
        predicates_info = []
        for fluent in up_problem.fluents:
            params = {}
            for param in fluent.signature:
                param_type = param.type.name if hasattr(param.type, 'name') else str(param.type)
                params[f"?{param.name}"] = param_type
            predicates_info.append({"name": fluent.name, "parameters": params})

        # Actions
        actions_info = []
        for action in up_problem.actions:
            params = {}
            for param in action.parameters:
                param_type = param.type.name if hasattr(param.type, 'name') else str(param.type)
                params[f"?{param.name}"] = param_type

            # Preconditions
            precond_parts = []
            for precond in action.preconditions:
                precond_parts.append(self._fnode_to_pddl(precond))
            if len(precond_parts) == 1:
                precond_str = precond_parts[0]
            elif precond_parts:
                precond_str = f"(and {' '.join(precond_parts)})"
            else:
                precond_str = "()"

            # Effects
            effect_parts = []
            for effect in action.effects:
                fluent_str = self._fnode_to_pddl(effect.fluent)
                if effect.value.is_true():
                    eff_str = fluent_str
                elif effect.value.is_false():
                    eff_str = f"(not {fluent_str})"
                else:
                    continue
                if effect.is_conditional():
                    cond_str = self._fnode_to_pddl(effect.condition)
                    eff_str = f"(when {cond_str} {eff_str})"
                effect_parts.append(eff_str)
            if len(effect_parts) == 1:
                effect_str = effect_parts[0]
            elif effect_parts:
                effect_str = f"(and {' '.join(effect_parts)})"
            else:
                effect_str = "()"

            actions_info.append({
                "name": action.name,
                "parameters": params,
                "precondition": precond_str,
                "effect": effect_str,
            })

        # Requirements — prefer PDDL source, fall back to ProblemKind inference
        pddl_reqs = self._extract_requirements_from_pddl(domain_path) if domain_path else None
        if pddl_reqs is not None:
            requirements = pddl_reqs
        else:
            requirements = [":strips"]
            try:
                kind = up_problem.kind
                if up_problem.user_types:
                    requirements.append(":typing")
                if kind.has_negative_conditions():
                    requirements.append(":negative-preconditions")
                if kind.has_disjunctive_conditions():
                    requirements.append(":disjunctive-preconditions")
                if kind.has_existential_conditions():
                    requirements.append(":existential-preconditions")
                if kind.has_universal_conditions():
                    requirements.append(":universal-preconditions")
                if kind.has_conditional_effects():
                    requirements.append(":conditional-effects")
                if kind.has_equalities():
                    requirements.append(":equality")
            except Exception:
                if up_problem.user_types:
                    requirements.append(":typing")

        return DomainInfo(
            name=domain_name or up_problem.name,
            requirements=sorted(requirements),
            types=types_info,
            predicates=predicates_info,
            actions=actions_info,
        )

