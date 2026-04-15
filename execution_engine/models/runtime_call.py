from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class RuntimeCall:
    """A concrete method invocation ready for the runtime adapter.

    Produced by the mapper from a validated Step: the step type is looked
    up in the capability registry to obtain the one method that executes it,
    and the step params are translated into the method's runtime variables.

    method_name: FluentControl method to invoke
    variables:   key-value pairs passed to SetVariableValue
    step_id:     mirrors the originating Step.id for traceability
    """
    method_name: str
    variables: Dict[str, Any] = field(default_factory=dict)
    step_id: Optional[str] = None
