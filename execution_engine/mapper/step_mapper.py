from typing import List

from ..capability_registry.registry import CapabilityRegistry
from ..models.runtime_call import RuntimeCall
from ..models.workflow import Step, Workflow
from .variable_mapper import VariableMapper


class MapperError(Exception):
    """Raised when a step cannot be mapped to a runtime call.

    Indicates a registry gap (no method supports this step type, or
    multiple methods are registered for it). Normal authored IRs never
    trigger this — validation plus the one-method-per-step-type invariant
    keep the mapping total.
    """


class StepMapper:
    """Direct 1:1 mapping from a validated Step to a RuntimeCall.

    The capability registry guarantees that each step type is supported
    by exactly one method, so no candidate selection or scoring is
    required. Mapping is therefore purely mechanical:

        1. Look up the single method whose `supports` list contains the
           step type (registry.methods_supporting(step.type)).
        2. Translate the step's params into the method's runtime variable
           dict via VariableMapper.

    Raises MapperError if zero or multiple methods are registered for a
    step type — both indicate a registry bug, not a runtime condition.
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
                "Add one to registry.yaml or remove the step."
            )
        if len(methods) > 1:
            names = ", ".join(m.name for m in methods)
            raise MapperError(
                f"Step type '{step.type}' is ambiguous: {len(methods)} methods "
                f"claim to support it ({names}). The registry must have exactly "
                "one method per step type."
            )

        method = methods[0]
        variables = self.variable_mapper.map(step)

        return RuntimeCall(
            method_name=method.name,
            variables=variables,
            step_id=step.id,
        )

    def map_workflow(self, workflow: Workflow) -> List[RuntimeCall]:
        """Map every step in a workflow in order."""
        return [self.map(step) for step in workflow.steps]
