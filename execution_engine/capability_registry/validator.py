"""Registry self-validation.

Runs at load time (or on demand) to detect internal inconsistencies
such as methods referencing tip types that don't exist.
This is separate from workflow validation.
"""
from .registry import CapabilityRegistry
from .models import ValidationResult, ValidationIssue


class RegistryValidator:
    """Checks a CapabilityRegistry for internal consistency."""

    def validate(self, registry: CapabilityRegistry) -> ValidationResult:
        result = ValidationResult()

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

        return result
