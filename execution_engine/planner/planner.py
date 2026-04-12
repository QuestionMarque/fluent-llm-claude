from typing import List

from ..capability_registry.registry import CapabilityRegistry
from ..models.workflow import Step
from ..models.plan import Plan
from .candidate_selector import CandidateSelector
from .scoring import ScoringEngine
from .variable_mapper import VariableMapper


class PlannerError(Exception):
    pass


class Planner:
    """Orchestrates the three-stage planning algorithm.

    Stage 1 — CandidateSelector (hard filter):
        Eliminates methods that cannot physically execute this step.
        Checks step type support, tip type, volume range, liquid compatibility.

    Stage 2 — ScoringEngine (soft ranking):
        Scores remaining candidates on a weighted multi-dimensional metric.
        Returns the best method with a score and reasoning trace.

    Stage 3 — VariableMapper (runtime mapping):
        Translates step params into the exact runtime variable dict
        expected by the chosen method's SetVariableValue calls.
    """

    def __init__(self, registry: CapabilityRegistry, enable_liquid_inference: bool = False):
        self.registry = registry
        self.selector = CandidateSelector(registry, enable_liquid_inference)
        self.scorer = ScoringEngine(registry)
        self.mapper = VariableMapper()

    def plan(self, step: Step) -> Plan:
        """Plan a single step. Raises PlannerError if no candidate found."""
        # Stage 1
        candidates = self.selector.select(step)
        if not candidates:
            raise PlannerError(
                f"No method candidate found for step type '{step.type}'. "
                "Check that the registry has methods supporting this step type "
                "and that the step parameters satisfy volume/tip constraints."
            )

        # Stage 2: score all candidates, pick the best
        scored = [(m, *self.scorer.score(step, m)) for m in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_method, best_score, reasoning = scored[0]

        # Stage 3: map to runtime variables
        variables = self.mapper.map(step, best_method.name)

        return Plan(
            method_name=best_method.name,
            variables=variables,
            score=best_score,
            reasoning=reasoning,
            step_id=step.id,
        )

    def plan_workflow(self, steps: List[Step]) -> List[Plan]:
        """Plan every step in a workflow. Raises PlannerError on first failure."""
        return [self.plan(step) for step in steps]
