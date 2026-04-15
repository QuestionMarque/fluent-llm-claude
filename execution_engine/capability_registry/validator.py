"""Registry self-validation.

Runs at load time to detect internal inconsistencies in the
CapabilityRegistry, such as:

- methods referencing tip types or liquid classes that don't exist
- the same step type claimed by multiple methods (ambiguous mapping)
- a step type declared in STEP_SCHEMA with no method to execute it

The first class produces warnings (the registry is usable but its
metadata is suspect). The latter two produce errors and cause
`load_registry()` to refuse the registry — they make the 1:1
step→method invariant that `mapper.StepMapper` relies on impossible
to satisfy.
"""
from collections import defaultdict
from typing import Iterable, Optional

from ..models.workflow import STEP_SCHEMA
from .registry import CapabilityRegistry
from .models import ValidationResult, ValidationIssue


class RegistryValidator:
    """Checks a CapabilityRegistry for internal consistency."""

    def validate(
        self,
        registry: CapabilityRegistry,
        expected_step_types: Optional[Iterable[str]] = None,
    ) -> ValidationResult:
        """Validate `registry`.

        `expected_step_types` defaults to the keys of `STEP_SCHEMA` —
        i.e. every step type the rest of the system understands must
        be supported by exactly one registered method. Pass an empty
        iterable to skip the coverage check (useful in unit tests
        that build minimal registries).
        """
        result = ValidationResult()

        if expected_step_types is None:
            expected_step_types = STEP_SCHEMA.keys()

        # --- Cross-reference checks (warnings) ---

        for method_name, method in registry.methods.items():
            for tip_name in method.tip_types:
                if tip_name not in registry.tips:
                    result.issues.append(ValidationIssue(
                        severity="warning",
                        message=f"Method '{method_name}' references unknown tip '{tip_name}'.",
                        context=method_name,
                    ))
            for lc_name in method.liquid_classes:
                if lc_name not in registry.liquid_classes:
                    result.issues.append(ValidationIssue(
                        severity="warning",
                        message=f"Method '{method_name}' references unknown liquid class '{lc_name}'.",
                        context=method_name,
                    ))

        for tip_name, liquids in registry.tip_liquid_compatibility.items():
            if tip_name not in registry.tips:
                result.issues.append(ValidationIssue(
                    severity="warning",
                    message=f"Compatibility matrix references unknown tip '{tip_name}'.",
                ))
            for lc_name in liquids:
                if lc_name not in registry.liquid_classes:
                    result.issues.append(ValidationIssue(
                        severity="warning",
                        message=f"Compatibility matrix references unknown liquid class '{lc_name}'.",
                    ))

        # --- Step-type → method invariant (errors) ---
        # The mapper relies on exactly one method per step type. Catching
        # violations here turns a per-step runtime failure into a single
        # load-time failure with a clear diagnostic.

        supporters = defaultdict(list)
        for method_name, method in registry.methods.items():
            for step_type in method.supports:
                supporters[step_type].append(method_name)

        # Ambiguity: more than one method claims a step type.
        for step_type, names in supporters.items():
            if len(names) > 1:
                result.issues.append(ValidationIssue(
                    severity="error",
                    message=(
                        f"Step type '{step_type}' is supported by {len(names)} methods "
                        f"({', '.join(names)}). Each step type must be supported by "
                        "exactly one method (the mapper has no selection logic)."
                    ),
                    context=step_type,
                ))

        # Coverage: a step type the system knows about has no method.
        for step_type in expected_step_types:
            if step_type not in supporters:
                result.issues.append(ValidationIssue(
                    severity="error",
                    message=(
                        f"No method in the registry supports step type '{step_type}'. "
                        "Add one to registry.yaml or remove the step type from STEP_SCHEMA."
                    ),
                    context=step_type,
                ))

        return result
