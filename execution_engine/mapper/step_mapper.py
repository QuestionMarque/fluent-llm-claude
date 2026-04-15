from typing import List

from ..capability_registry.registry import CapabilityRegistry
from ..models.runtime_call import RuntimeCall
from ..models.workflow import Step, Workflow
from .variable_mapper import VariableMapper


class MapperError(Exception):
    """Raised when a step cannot be mapped to a runtime call.

    The only path that produces this is `step.type` not being declared
    in any registered method's `supports` list. For library and LLM IRs
    this can never happen — validation rejects unknown step types
    upstream, and the registry loader refuses any registry that doesn't
    cover every type in STEP_SCHEMA. The check remains as a defensive
    guard for direct callers that bypass validation.
    """


class StepMapper:
    """Direct 1:1 mapping from a validated Step to a RuntimeCall.

    The capability registry guarantees that each step type is supported
    by exactly one method (enforced at load time by RegistryValidator),
    so no candidate selection or scoring is required. Mapping is purely
    mechanical:

        1. Look up the single method whose `supports` list contains the
           step type (`registry.methods_supporting(step.type)`).
        2. Translate the step's params into the method's runtime variable
           dict via VariableMapper.
    """

    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry
        self.variable_mapper = VariableMapper()

    def map(self, step: Step) -> RuntimeCall:
        """Map a single step to a RuntimeCall."""
        methods = self.registry.methods_supporting(step.type)
        if not methods:
            raise MapperError(
                f"No method in the registry supports step type '{step.type}'. "
                "The step type is unknown — validation should have rejected it."
            )

        return RuntimeCall(
            method_name=methods[0].name,
            variables=self.variable_mapper.map(step),
            step_id=step.id,
        )

    def map_workflow(self, workflow: Workflow) -> List[RuntimeCall]:
        """Map every step in a workflow in order."""
        return [self.map(step) for step in workflow.steps]
