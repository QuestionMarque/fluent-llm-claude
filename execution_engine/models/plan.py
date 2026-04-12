from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Plan:
    """Output contract from the Planner for a single Step.

    method_name: the FluentControl method to invoke
    variables:   key-value pairs passed to SetVariableValue
    score:       composite score from ScoringEngine (higher = better fit)
    reasoning:   human-readable explanation of the selection
    step_id:     mirrors the originating Step.id for traceability
    """
    method_name: str
    variables: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    reasoning: str = ""
    step_id: Optional[str] = None
