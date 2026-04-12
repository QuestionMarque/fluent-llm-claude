from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FeedbackItem:
    """A single validation issue — error or warning.

    type:       short machine-readable category (e.g. "missing_required_field")
    message:    human-readable description of the issue
    suggestion: optional corrective action hint
    context:    optional step id or field name for traceability
    severity:   "error" blocks execution; "warning" is advisory
    """
    type: str
    message: str
    suggestion: Optional[str] = None
    context: Optional[str] = None
    severity: str = "error"  # "error" | "warning"


@dataclass
class ValidationFeedback:
    """Aggregated validation result for a workflow or step.

    errors:       FeedbackItems that block execution.
    warnings:     FeedbackItems that are advisory only.
    is_valid:     True only when errors list is empty.
    retry_prompt: optionally populated by FeedbackBuilder for LLM retry loops.
    """
    errors: List[FeedbackItem] = field(default_factory=list)
    warnings: List[FeedbackItem] = field(default_factory=list)
    retry_prompt: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0
